import time
import gc
import uasyncio as asyncio

from common.config_runtime import (
  cfg,
  front_motor_cfg,
  rear_motor_cfg,
)

from machine import WDT
from vars import Vars
from motor import MotorData, Motor
from brake import Brake
from throttle import Throttle
from common.utils import map_range
from common.espnow import espnow_init, ESPNowComms
from common.espnow_commands import COMMAND_ID_DISPLAY_1, COMMAND_ID_LIGHTS_1
from common.lights_bits import REAR_BRAKE_BIT
from mode import Mode

import neopixel
import machine
_led = neopixel.NeoPixel(machine.Pin(21, machine.Pin.OUT), 1)

# Object that holds various runtime variables
vars = Vars()

# Brake sensor
brake_sensor = Brake(cfg.brake_pin)

# If brakes are active at startup, block here (development safety)
while brake_sensor.value:
  print('brake at start')
  time.sleep(1)

motor_cfgs = [rear_motor_cfg]
if front_motor_cfg is not None:
  motor_cfgs.append(front_motor_cfg)

motor_datas = [MotorData(c) for c in motor_cfgs]
motors = [Motor(d) for d in motor_datas]

rear_motor_data = motor_datas[0]
rear_motor = motors[0]
front_motor_data = motor_datas[1] if len(motor_datas) > 1 else None
front_motor = motors[1] if len(motors) > 1 else None

# Init targets from configuration
for motor_data in motor_datas:
  motor_data.motor_target_current_limit_max = motor_data.cfg.motor_max_current_limit_max
  motor_data.motor_target_current_limit_min = motor_data.cfg.motor_max_current_limit_min
  motor_data.battery_target_current_limit_max = motor_data.cfg.battery_max_current_limit_max
  motor_data.battery_target_current_limit_min = motor_data.cfg.battery_max_current_limit_min

sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_motor_board)

display_peer_mac = bytes(cfg.mac_address_display)
lights_peer_mac = bytes(cfg.mac_address_lights)

def decode_display_message(msg):
  parts = [int(s) for s in msg.decode("ascii").split()]
  if len(parts) == 3 and parts[0] == COMMAND_ID_DISPLAY_1:
    return parts
  return None

def encode_display_message(vars, rear_motor_data, front_motor_data=None):
  brakes_are_active = 1 if vars.brakes_are_active else 0
  regen_braking_is_active = 1 if vars.regen_braking_is_active else 0
  battery_is_charging = 1 if vars.battery_is_charging else 0

  if not cfg.has_jbd_bms:
    battery_is_charging = 0

  motor_datas_local = [rear_motor_data]
  if front_motor_data is not None:
    motor_datas_local.append(front_motor_data)

  battery_current_x10 = sum(int(m.battery_current_x10) for m in motor_datas_local)
  motor_current_x10 = sum(int(m.motor_current_x10) for m in motor_datas_local)
  vesc_temperature_x10 = max(int(m.vesc_temperature_x10) for m in motor_datas_local)
  motor_temperature_x10 = max(int(m.motor_temperature_x10) for m in motor_datas_local)

  flags = ((brakes_are_active & 1) << 0) | \
          ((regen_braking_is_active & 1) << 1) | \
          ((battery_is_charging & 1) << 2) | \
          ((vars.mode & 7) << 3)

  return (
    f"{COMMAND_ID_DISPLAY_1} {int(rear_motor_data.battery_voltage_x10)} "
    f"{battery_current_x10} {int(rear_motor_data.battery_soc_x1000)} "
    f"{motor_current_x10} {int(rear_motor_data.wheel_speed * 10)} {int(flags)} "
    f"{int(vesc_temperature_x10)} {int(motor_temperature_x10)}"
  ).encode("ascii")

def encode_lights_message(mask, state):
  return (
    f"{COMMAND_ID_LIGHTS_1} {int(mask)} {int(state)}"
  ).encode("ascii")

display_comms = ESPNowComms(esp, decoder=decode_display_message, encoder=encode_display_message)
lights_tx_comms = ESPNowComms(esp, encoder=encode_lights_message)

# Optional BMS support (BLE) — BLE activation is deferred to bms.start()
if cfg.has_jbd_bms:
  import bluetooth
  from bms_jbd import JbdBmsClient

  # Create a single BLE instance; don't call active(True) here.
  ble = bluetooth.BLE()
  bms = JbdBmsClient(
    ble=ble,
    target_name=cfg.jbd_bms_bluetooth_name,
    query_period_ms=1000,
    interleave_cells=True,
    debug=True,
  )

  async def bms_task(bms: JbdBmsClient):
    """
    Drive the client's cooperative state machine:
    - drain BLE notifications
    - schedule 0x03/0x04 polls
    - keep reconnect logic responsive
    NOTE: we start BLE only after ESP-NOW is up and we've paused briefly.
    """
    # Give Wi-Fi/ESP-NOW a moment to settle before starting BLE (coex-friendly)
    await asyncio.sleep_ms(300)
    bms.start(scan_ms=8000)  # start() will activate BLE with small retries
    while True:
      bms.tick()
      await asyncio.sleep_ms(50)  # ~20 Hz tick

  async def bms_read_task(bms: JbdBmsClient):
    """
    Periodically read cached data. No blocking, no BLE calls here.
    """
    while True:
      if bms.is_connected() and bms.is_fresh(3000):
        vars.bms_battery_current_x100 = bms.get_current_a_x100()
      await asyncio.sleep_ms(1000)  # read cadence

# Throttles
throttle_1 = Throttle(
  cfg.throttle_1_pin,
  min_val=cfg.throttle_1_adc_min,   # min ADC (with margin)
  max_val=cfg.throttle_1_adc_max,   # max ADC (with margin)
)

throttle_2 = None
if hasattr(cfg, "throttle_2_pin"):
  throttle_2 = Throttle(
    cfg.throttle_2_pin,
    min_val=cfg.throttle_2_adc_min,
    max_val=cfg.throttle_2_adc_max,
  )

mode = Mode(brake_sensor, throttle_1, vars, save_to_nvs=cfg.save_mode_to_nvs)

async def task_motors_refresh_data():
  # Refresh latest VESC data (call once; it fills both via CAN)
  while True:
    if front_motor is None:
      rear_motor.update_motor_data(rear_motor, None)
    else:
      rear_motor.update_motor_data(rear_motor, front_motor)
    gc.collect()
    await asyncio.sleep(0.05)

async def task_display_send_data():
  while True:
    if front_motor_data is None:
      display_comms.send_data(display_peer_mac, vars, rear_motor_data)
    else:
      display_comms.send_data(display_peer_mac, vars, rear_motor_data, front_motor_data)
    gc.collect()
    await asyncio.sleep(0.25)

async def task_lights_send_data():
  while True:
    brake_bit = REAR_BRAKE_BIT if vars.brakes_are_active else 0
    lights_tx_comms.send_data(lights_peer_mac, REAR_BRAKE_BIT, brake_bit)
    gc.collect()
    await asyncio.sleep(0.1)

async def task_display_receive_process_data():
  while True:
    msg = display_comms.get_data()
    if msg is not None:
      vars.motors_enable_state = (msg[1] != 0)
      vars.buttons_state = msg[2]
    gc.collect()
    await asyncio.sleep(0.1)

def cruise_control(vars, wheel_speed, throttle_value):
  button_long_press_state = vars.buttons_state & 0x0200

  # Init
  if vars.cruise_control.state == 0:
    vars.cruise_control.button_long_press_previous_state = button_long_press_state
    vars.cruise_control.state = 1

  # Wait to start cruise
  if vars.cruise_control.state == 1:
    if (button_long_press_state != vars.cruise_control.button_long_press_previous_state) and (wheel_speed > 4.0):
      vars.cruise_control.button_long_press_previous_state = button_long_press_state
      vars.cruise_control.throttle_value = throttle_value
      vars.cruise_control.state = 2

  # Cruise active
  if vars.cruise_control.state == 2:
    vars.cruise_control.button_pressed = False
    button_press_state = vars.buttons_state & 0x0100
    if button_press_state != vars.cruise_control.button_press_previous_state:
      vars.cruise_control.button_press_previous_state = button_press_state
      vars.cruise_control.button_pressed = True

    # Stop cruise?
    if vars.brakes_are_active or vars.cruise_control.button_pressed or throttle_value > (vars.cruise_control.throttle_value * 1.15):
      vars.cruise_control.button_long_press_previous_state = button_long_press_state
      vars.cruise_control.state = 1
    else:
      # Keep cruising: override throttle
      throttle_value = vars.cruise_control.throttle_value

  return throttle_value

def _read_throttle(throttle):
  raw, mapped = throttle.value
  return raw, mapped

async def task_control_motor(wdt):
  while True:
    motor_erpm_max_speed_limits = [
      motor_data.cfg.motor_erpm_max_speed_limit[vars.mode]
      for motor_data in motor_datas
    ]

    # Throttle: take max of available throttles
    throttle_1_raw, throttle_1_value = _read_throttle(throttle_1)
    throttle_value = throttle_1_value

    throttle_2_raw = None
    throttle_2_value = None
    if throttle_2 is not None:
      throttle_2_raw, throttle_2_value = _read_throttle(throttle_2)
      throttle_value = max(throttle_value, throttle_2_value)

    # Over-max safety (ADC glitch protection)
    if throttle_1_raw > cfg.throttle_1_adc_over_max_error:
      for _ in range(3):
        for motor in motors:
          motor.set_motor_current_amps(0)
      raise Exception(f'throttle 1 value: {throttle_1_raw} -- is over max, this can be dangerous!')

    if throttle_2_raw is not None:
      throttle_2_over_max = getattr(cfg, "throttle_2_adc_over_max_error", None)
      if throttle_2_over_max is not None and throttle_2_raw > throttle_2_over_max:
        for _ in range(3):
          for motor in motors:
            motor.set_motor_current_amps(0)
        raise Exception(f'throttle 2 value: {throttle_2_raw} -- is over max, this can be dangerous!')

    # Cruise control
    throttle_value = cruise_control(vars, rear_motor.data.wheel_speed, throttle_value)

    # Target speed (map 0..1000 → 0..ERPM limit)
    for motor_data, motor_erpm_max_speed_limit in zip(motor_datas, motor_erpm_max_speed_limits):
      motor_data.motor_target_speed = map_range(
        throttle_value, 0.0, 1000.0, 0.0, motor_erpm_max_speed_limit, clamp=True
      )

      # Small dead-zone
      if motor_data.motor_target_speed < 500.0:
        motor_data.motor_target_speed = 0.0

      # Enforce max
      if motor_data.motor_target_speed > motor_erpm_max_speed_limit:
        motor_data.motor_target_speed = motor_erpm_max_speed_limit

    # Set motor/battery current limits
    for motor in motors:
      motor.set_motor_current_limits(
        motor.data.motor_target_current_limit_min,
        motor.data.motor_target_current_limit_max)

      motor.set_battery_current_limits(
        motor.data.battery_target_current_limit_min,
        motor.data.battery_target_current_limit_max)

    # Brakes
    vars.brakes_are_active = True if brake_sensor.value else False

    # Consider less then 10 negative amps of motor current for regen_brakes_are_active = True
    motor_current = sum(motor.data.motor_current_x10 for motor in motors) // 10
    vars.regen_braking_is_active = True if motor_current < -10 else False

    # Command motor(s)
    if vars.motors_enable_state is False:
      for motor in motors:
        motor.set_motor_current_amps(0)
    else:
      if vars.brakes_are_active:
        for motor in motors:
          motor.set_motor_speed_rpm(0)
      else:
        for motor in motors:
          motor.set_motor_speed_rpm(motor.data.motor_target_speed)

    if wdt is not None:
      wdt.feed()

    gc.collect()
    await asyncio.sleep(0.02)

async def task_control_motor_limit_current():
  while True:
    # Always use rear wheel speed
    wheel_speed = rear_motor.data.wheel_speed

    for motor_data in motor_datas:
      motor_data.motor_target_current_limit_max = map_range(
        wheel_speed,
        5.0,
        motor_data.cfg.motor_current_limit_max_min_speed,
        motor_data.cfg.motor_current_limit_max_max,
        motor_data.cfg.motor_current_limit_max_min,
        clamp=True)

      motor_data.motor_target_current_limit_min = map_range(
        wheel_speed,
        5.0,
        motor_data.cfg.motor_current_limit_min_max_speed,
        motor_data.cfg.motor_current_limit_min_max,
        motor_data.cfg.motor_current_limit_min_min,
        clamp=True)

      motor_data.battery_target_current_limit_max = map_range(
        wheel_speed,
        5.0,
        motor_data.cfg.battery_current_limit_max_min_speed,
        motor_data.cfg.battery_current_limit_max_max,
        motor_data.cfg.battery_current_limit_max_min,
        clamp=True)

      motor_data.battery_target_current_limit_min = map_range(
        wheel_speed,
        5.0,
        motor_data.cfg.battery_current_limit_min_max_speed,
        motor_data.cfg.battery_current_limit_min_max,
        motor_data.cfg.battery_current_limit_min_min,
        clamp=True)

    gc.collect()
    await asyncio.sleep(0.1)

_led_state = False
def _led_blink():
  global _led_state
  _led_state = not _led_state
  if _led_state:
    _led[0] = (0, 4, 0)
  else:
    _led[0] = (4, 0, 0)

  _led.write()

async def task_various():
  wheel_speed_previous_motor_speed_erpm = 0
  charge_seen_ms = False
  global mode

  while True:
    # Calculate rear motor wheel speed
    if rear_motor.data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
      wheel_speed_previous_motor_speed_erpm = rear_motor.data.speed_erpm

      # 2*pi ≈ 6.28318
      perimeter = 6.28318 * rear_motor.data.cfg.wheel_radius  # meters
      motor_rpm = rear_motor.data.speed_erpm / max(1, rear_motor.data.cfg.poles_pair)
      rear_motor.data.wheel_speed = (perimeter * motor_rpm * 60.0) / 1000.0  # km/h

      # Small floor near zero
      if abs(rear_motor.data.wheel_speed) < 2.0:
        rear_motor.data.wheel_speed = 0.0

    # Auto-detect charging
    # Note: BMS battery current is positive when charging
    if cfg.has_jbd_bms:
      now = time.ticks_ms()
      if rear_motor.data.wheel_speed == 0 and \
              vars.bms_battery_current_x100 is not None and \
              vars.bms_battery_current_x100 > cfg.charge_current_threshold_a_x100:
        if charge_seen_ms is None:
          charge_seen_ms = now
        elif time.ticks_diff(now, charge_seen_ms) >= cfg.charge_detect_hold_ms:
          vars.battery_is_charging = True
      else:
        vars.battery_is_charging = False
        charge_seen_ms = None

    # Run Mode tick
    mode.tick()

    _led_blink()

    gc.collect()
    await asyncio.sleep(0.1)

async def main():
  # Watchdog (min 1s on ESP32). task_control_motor() feeds it continuously.
  wdt = WDT(timeout=1000)

  # Build the task list
  tasks = [
    asyncio.create_task(task_motors_refresh_data()),
    asyncio.create_task(task_control_motor_limit_current()),
    asyncio.create_task(task_control_motor(wdt)),
    asyncio.create_task(task_display_send_data()),
    asyncio.create_task(task_lights_send_data()),
    asyncio.create_task(task_display_receive_process_data()),
    asyncio.create_task(task_various()),
  ]

  # Add BMS tasks only if enabled in config
  if cfg.has_jbd_bms:
    tasks.append(asyncio.create_task(bms_task(bms)))
    tasks.append(asyncio.create_task(bms_read_task(bms)))

  print("Starting EBike/EScooter\n")

  # Wait for all tasks (keeps main alive; propagates exceptions)
  await asyncio.gather(*tasks)

asyncio.run(main())
