import time
import gc
import uasyncio as asyncio

import common.config_runtime as cfg

from machine import WDT
from vars import Vars
from motor import MotorData, Motor
from brake import Brake
from throttle import Throttle
from common.utils import map_range
from common.espnow import espnow_init, ESPNowComms, espnow_recv_last
from common.espnow_protocol import (
  BOARD_DISPLAY,
  BOARD_LIGHTS,
  BOARD_MOTOR,
  MSG_COMMAND,
  MSG_STATUS,
  HEALTH_MOTOR_LIGHTS_TX_OK,
  build_command,
  build_status,
  parse_frame,
)
from common.lights_bits import REAR_BRAKE_BIT
from mode import Mode

TEMPERATURE_NOT_AVAILABLE_X10 = -2550
DISPLAY_MOTORS_ENABLE_TIMEOUT_MS = 2000
DISPLAY_MOTORS_ENABLE_BOOT_GRACE_MS = 20000
system_boot_ms = time.ticks_ms()

try:
  import neopixel
  import machine
  _led = neopixel.NeoPixel(machine.Pin(21, machine.Pin.OUT), 1)
except Exception:
  _led = None

print('EBike/EScooter type: ' + cfg.type_name)
print()

# Brake sensor
brake_sensor = Brake(cfg.brake_pin)

# If brakes are active at startup, hold for 20 seconds and then latch
# the board until the next power cycle.
if brake_sensor.value:
  boot_block_ms = 20000
  boot_block_start_ms = time.ticks_ms()
  seconds_reported = -1

  while time.ticks_diff(time.ticks_ms(), boot_block_start_ms) < boot_block_ms:
    if not brake_sensor.value:
      print('Startup resumed: brake released before timeout')
      break

    elapsed_ms = time.ticks_diff(time.ticks_ms(), boot_block_start_ms)
    seconds_elapsed = elapsed_ms // 1000

    if seconds_elapsed != seconds_reported:
      seconds_reported = seconds_elapsed
      seconds_left = max(0, 20 - seconds_elapsed)
      print(f'Startup blocked: brake active at boot, hanging in {seconds_left}s')

    time.sleep_ms(100)
  else:
    print('Startup blocked: brake held at boot, waiting for next power cycle')
    while True:
      time.sleep(1)

# Object that holds various runtime variables
vars = Vars()
display_motors_enable_last_seen_ms = None

# ESPNow wireless communications  
sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_motor_board)

def decode_display_command(msg):
  parts = parse_frame(msg)
  if parts is None:
    return None
  if len(parts) == 7 and parts[0] == MSG_COMMAND and parts[1] == BOARD_DISPLAY and parts[2] == BOARD_MOTOR:
    return parts
  return None

def encode_display_status(vars, rear_motor_data, front_motor_data=None):
  brakes_are_active = 1 if vars.brakes_are_active else 0
  regen_braking_is_active = 1 if vars.regen_braking_is_active else 0
  battery_is_charging = 1 if vars.battery_is_charging else 0
  cruise_control_is_active = 1 if vars.cruise_control.state == 2 else 0
  throttle_active = 1 if vars.throttle_value > 50 else 0
  throttle_right_fault = 1 if vars.throttle_right_fault else 0
  throttle_left_fault = 1 if vars.throttle_left_fault else 0

  if not cfg.has_jbd_bms:
    battery_is_charging = 0

  motor_datas_local = [rear_motor_data]
  if front_motor_data is not None:
    motor_datas_local.append(front_motor_data)

  battery_current_x10 = sum(int(m.battery_current_x10) for m in motor_datas_local)
  motor_current_x10 = sum(int(m.motor_current_x10) for m in motor_datas_local)
  front_vesc_temperature_x10 = int(front_motor_data.vesc_temperature_x10) if front_motor_data is not None else TEMPERATURE_NOT_AVAILABLE_X10
  front_motor_temperature_x10 = int(front_motor_data.motor_temperature_x10) if front_motor_data is not None else TEMPERATURE_NOT_AVAILABLE_X10

  flags = ((brakes_are_active & 1) << 0) | \
          ((regen_braking_is_active & 1) << 1) | \
          ((battery_is_charging & 1) << 2) | \
          ((vars.mode & 7) << 3) | \
          ((cruise_control_is_active & 1) << 6) | \
          ((throttle_active & 1) << 7) | \
          ((throttle_right_fault & 1) << 8) | \
          ((throttle_left_fault & 1) << 9)

  health_bitmap = HEALTH_MOTOR_LIGHTS_TX_OK if vars.lights_comm_ok else 0

  return build_status(
    BOARD_MOTOR,
    BOARD_DISPLAY,
    health_bitmap,
    int(rear_motor_data.battery_voltage_x10),
    battery_current_x10,
    int(rear_motor_data.battery_soc_x1000),
    motor_current_x10,
    int(rear_motor_data.wheel_speed * 10),
    int(flags),
    int(rear_motor_data.vesc_temperature_x10),
    front_vesc_temperature_x10,
    int(rear_motor_data.motor_temperature_x10),
    front_motor_temperature_x10,
  )

def encode_lights_message(mask, state):
  return build_command(
    BOARD_MOTOR,
    BOARD_LIGHTS,
    int(mask),
    int(state),
  )

display_status_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_display),
  encoder=encode_display_status,
)

lights_tx_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_lights),
  encoder=encode_lights_message)

motor_cfgs = [cfg.rear_motor_cfg]
if cfg.front_motor_cfg is not None:
  motor_cfgs.append(cfg.front_motor_cfg)

motor_data = [MotorData(c) for c in motor_cfgs]
motors = [Motor(d) for d in motor_data]

rear_motor_data = motor_data[0]
rear_motor = motors[0]
front_motor_data = motor_data[1] if len(motor_data) > 1 else None
front_motor = motors[1] if len(motors) > 1 else None

# Init targets from configuration
for _motor_data in motor_data:
  _motor_data.motor_target_current_limit_max = _motor_data.cfg.motor_max_current_limit_max
  _motor_data.motor_target_current_limit_min = _motor_data.cfg.motor_max_current_limit_min
  _motor_data.battery_target_current_limit_max = _motor_data.cfg.battery_max_current_limit_max
  _motor_data.battery_target_current_limit_min = _motor_data.cfg.battery_max_current_limit_min

# Optional BMS support (BLE). The client may activate BLE when created;
# scanning is deferred to bms.start().
if cfg.has_jbd_bms:
  import bluetooth
  from bms_jbd import JbdBmsClient

  # Create a single BLE instance. Only BLE scanning is delayed below.
  ble = bluetooth.BLE()
  bms = JbdBmsClient(
    ble=ble,
    target_name=cfg.jbd_bms_bluetooth_name,
    query_period_ms=1000,
    interleave_cells=True,
    debug=getattr(cfg, "bms_debug", False),
  )

  async def bms_task(bms: JbdBmsClient):
    """
    Drive the client's cooperative state machine:
    - drain BLE notifications
    - schedule 0x03/0x04 polls
    - keep reconnect logic responsive
    NOTE: BLE scanning starts only after ESP-NOW is up and we've paused briefly.
    """
    # Give Wi-Fi/ESP-NOW a moment to settle before starting BLE scanning.
    await asyncio.sleep_ms(300)
    bms.start(scan_ms=8000)
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

throttle_2_pin = getattr(cfg, 'throttle_2_pin', None)
if throttle_2_pin is None:
  throttle_2 = None
else:
  throttle_2 = Throttle(
    throttle_2_pin,
    min_val=cfg.throttle_2_adc_min,
    max_val=cfg.throttle_2_adc_max,
  )

throttle_1_disabled = False
throttle_2_disabled = throttle_2 is None

mode = Mode(brake_sensor, (throttle_1, throttle_2), vars, save_to_nvs=cfg.save_mode_to_nvs)

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
  period_ms = 250
  next_wake = time.ticks_ms()
  while True:
    if front_motor_data is None:
      vars.display_comm_ok = display_status_comms.send_data(vars, rear_motor_data)
    else:
      vars.display_comm_ok = display_status_comms.send_data(vars, rear_motor_data, front_motor_data)
    
    gc.collect()
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def task_lights_send_data():
  while True:
    if vars.brakes_are_active or vars.regen_braking_is_active:
      brake_bit = REAR_BRAKE_BIT
    else:
      brake_bit = 0

    vars.lights_comm_ok = lights_tx_comms.send_data(REAR_BRAKE_BIT, brake_bit)

    gc.collect()
    await asyncio.sleep(0.1)

async def task_espnow_receive_process_data():
  global display_motors_enable_last_seen_ms

  while True:
    packet = espnow_recv_last(esp)
    if packet is not None:
      host, msg = packet
      parts = parse_frame(msg)
      if parts is not None and len(parts) == 7 and parts[0] == MSG_COMMAND and parts[1] == BOARD_DISPLAY and parts[2] == BOARD_MOTOR:
        vars.display_comm_ok = True
        vars.motors_enable_state = bool(parts[3])
        display_motors_enable_last_seen_ms = time.ticks_ms()
        vars.buttons_state = parts[4]
        vars.turn_off_relay = bool(parts[6])

    gc.collect()
    await asyncio.sleep(0.1)

def cruise_control(vars, wheel_speed, requested_motor_target_speed):
  button_long_press_state = vars.buttons_state & 0x0200
  button_press_state = vars.buttons_state & 0x0100

  # Init
  if vars.cruise_control.state == 0:
    vars.cruise_control.button_long_press_previous_state = button_long_press_state
    vars.cruise_control.button_press_previous_state = button_press_state
    vars.cruise_control.state = 1

  # Wait to start cruise
  if vars.cruise_control.state == 1:
    if (button_long_press_state != vars.cruise_control.button_long_press_previous_state) and (wheel_speed > 2.0):
      vars.cruise_control.button_long_press_previous_state = button_long_press_state
      vars.cruise_control.button_press_previous_state = button_press_state
      vars.cruise_control.target_motor_speed = wheel_speed_to_motor_erpm(
        wheel_speed,
        rear_motor.data.cfg,
      )
      vars.cruise_control.manual_cancel_ready = False
      vars.cruise_control.state = 2

  # Cruise active
  elif vars.cruise_control.state == 2:
    vars.cruise_control.button_pressed = False
    if button_press_state != vars.cruise_control.button_press_previous_state:
      vars.cruise_control.button_press_previous_state = button_press_state
      vars.cruise_control.button_pressed = True

    if requested_motor_target_speed < (vars.cruise_control.target_motor_speed * 0.80):
      vars.cruise_control.manual_cancel_ready = True

    manual_cancel_requested = False
    if vars.cruise_control.manual_cancel_ready and \
            requested_motor_target_speed > vars.cruise_control.target_motor_speed:
      manual_cancel_requested = True

    # Stop cruise?
    if vars.brakes_are_active or vars.cruise_control.button_pressed or manual_cancel_requested:
      vars.cruise_control.button_long_press_previous_state = button_long_press_state
      vars.cruise_control.target_motor_speed = 0.0
      vars.cruise_control.manual_cancel_ready = False
      vars.cruise_control.state = 1

  return vars.cruise_control.state == 2

def wheel_speed_to_motor_erpm(wheel_speed, motor_cfg):
  if motor_cfg.wheel_radius <= 0:
    return 0.0
  perimeter = 6.28318 * motor_cfg.wheel_radius  # meters
  motor_rpm = (wheel_speed * 1000.0) / max(1.0, perimeter * 60.0)
  return motor_rpm * max(1, motor_cfg.poles_pair)

def _stop_motors():
  for _ in range(3):
    for motor in motors:
      motor.set_motor_current_amps(0)

async def task_control_motor(wdt):
  global throttle_1_disabled, throttle_2_disabled
  global display_motors_enable_last_seen_ms
  _release_condition_since_ms = None

  # Hall-effect throttle supply can spike above over-max threshold at power-on;
  # a single bad reading permanently sets throttle_1_disabled with no recovery path.
  await asyncio.sleep_ms(500)

  while True:
    motor_erpm_max_speed_limits = [
      _motor_data.cfg.motor_erpm_max_speed_limit[vars.mode]
      for _motor_data in motor_data
    ]

    # Throttle: take max of available throttles
    throttle_1_raw, throttle_1_value = throttle_1.value
    if throttle_1_disabled:
      throttle_1_value = 0
    throttle_value = throttle_1_value

    throttle_2_raw = None
    throttle_2_value = None
    if throttle_2 is not None:
      throttle_2_raw, throttle_2_value = throttle_2.value
      if throttle_2_disabled:
        throttle_2_value = 0
      throttle_value = max(throttle_value, throttle_2_value)

    # Over-max safety (ADC glitch protection):
    # disable the affected throttle first; only stop with exception if both fail.
    throttle_1_over_max = throttle_1_raw > cfg.throttle_1_adc_over_max_error
    if throttle_1_over_max:
      throttle_1_disabled = True
      throttle_1_value = 0

    throttle_2_over_max = False
    if throttle_2_raw is not None:
      throttle_2_over_max = throttle_2_raw > cfg.throttle_2_adc_over_max_error
      if throttle_2_over_max:
        throttle_2_disabled = True
        throttle_2_value = 0

    throttle_value = max(throttle_1_value, throttle_2_value or 0)
    vars.throttle_value = throttle_value
    vars.throttle_right_fault = throttle_1_disabled
    vars.throttle_left_fault = throttle_2_disabled and throttle_2 is not None

    if throttle_1_disabled and (throttle_2 is None or throttle_2_disabled):
      _stop_motors()
      raise Exception(
        f'both throttles disabled due to over-max ADC values: '
        f'throttle 1={throttle_1_raw}, throttle 2={throttle_2_raw}'
      )

    requested_motor_target_speed = map_range(
      throttle_value, 0.0, 1000.0, 0.0, motor_erpm_max_speed_limits[0], clamp=True
    )

    # Cruise control
    cruise_control_is_active = cruise_control(
      vars,
      rear_motor.data.wheel_speed,
      requested_motor_target_speed,
    )

    # Target speed
    for _motor_data, motor_erpm_max_speed_limit in zip(motor_data, motor_erpm_max_speed_limits):
      if cruise_control_is_active:
        _motor_data.motor_target_speed = vars.cruise_control.target_motor_speed
      else:
        _motor_data.motor_target_speed = map_range(
          throttle_value, 0.0, 1000.0, 0.0, motor_erpm_max_speed_limit, clamp=True
        )

      # Small dead-zone
      if _motor_data.motor_target_speed < 500.0:
        _motor_data.motor_target_speed = 0.0

      # Enforce max
      if _motor_data.motor_target_speed > motor_erpm_max_speed_limit:
        _motor_data.motor_target_speed = motor_erpm_max_speed_limit

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

    # Fail safe: if the display stops refreshing the enable command, drop to disabled state.
    # Give the display a startup grace window so Wi-Fi/NTP sync can pause ESP-NOW
    # without forcing the motor off immediately.
    if (
      vars.motors_enable_state and
      display_motors_enable_last_seen_ms is not None and
      time.ticks_diff(time.ticks_ms(), display_motors_enable_last_seen_ms) >= DISPLAY_MOTORS_ENABLE_TIMEOUT_MS and
      time.ticks_diff(time.ticks_ms(), system_boot_ms) >= DISPLAY_MOTORS_ENABLE_BOOT_GRACE_MS
    ):
        vars.motors_enable_state = False
        vars.display_comm_ok = False

    # Consider less then 10 negative amps of motor current for regen_brakes_are_active = True
    motor_current = sum(motor.data.motor_current_x10 for motor in motors) // 10
    vars.regen_braking_is_active = True if motor_current < -10 else False

    # Command motor(s)
    if vars.motors_enable_state is False:
      vars.cruise_control.target_motor_speed = 0.0
      vars.cruise_control.manual_cancel_ready = False
      vars.cruise_control.state = 1
      vars.cruise_control.button_press_previous_state = vars.buttons_state & 0x0100
      vars.cruise_control.button_long_press_previous_state = vars.buttons_state & 0x0200
      for motor in motors:
        motor.set_motor_current_amps(0)
    else:
      if vars.brakes_are_active:
        for motor in motors:
          motor.set_motor_speed_erpm(0)
      else:
        has_motor_target_speed = any(motor.data.motor_target_speed > 0 for motor in motors)
        release_condition_met = (not has_motor_target_speed) and rear_motor.data.wheel_speed == 0

        if release_condition_met:
          if _release_condition_since_ms is None:
            _release_condition_since_ms = time.ticks_ms()
          should_release_motors = time.ticks_diff(time.ticks_ms(), _release_condition_since_ms) >= 2000
        else:
          _release_condition_since_ms = None
          should_release_motors = False

        for motor in motors:
          if should_release_motors:
            motor.set_motor_current_amps(0)
          else:
            motor.set_motor_speed_erpm(motor.data.motor_target_speed)

    if wdt is not None:
      wdt.feed()

    gc.collect()
    await asyncio.sleep(0.02)

async def task_control_motor_limit_current():
  while True:
    # Always use rear wheel speed
    wheel_speed = rear_motor.data.wheel_speed

    for _motor_data in motor_data:
      _motor_data.motor_target_current_limit_max = map_range(
        wheel_speed,
        5.0,
        _motor_data.cfg.motor_current_limit_max_min_speed,
        _motor_data.cfg.motor_current_limit_max_max,
        _motor_data.cfg.motor_current_limit_max_min,
        clamp=True)

      _motor_data.motor_target_current_limit_min = map_range(
        wheel_speed,
        5.0,
        _motor_data.cfg.motor_current_limit_min_max_speed,
        _motor_data.cfg.motor_current_limit_min_max,
        _motor_data.cfg.motor_current_limit_min_min,
        clamp=True)

      _motor_data.battery_target_current_limit_max = map_range(
        wheel_speed,
        5.0,
        _motor_data.cfg.battery_current_limit_max_min_speed,
        _motor_data.cfg.battery_current_limit_max_max,
        _motor_data.cfg.battery_current_limit_max_min,
        clamp=True)

      _motor_data.battery_target_current_limit_min = map_range(
        wheel_speed,
        5.0,
        _motor_data.cfg.battery_current_limit_min_max_speed,
        _motor_data.cfg.battery_current_limit_min_max,
        _motor_data.cfg.battery_current_limit_min_min,
        clamp=True)

    gc.collect()
    await asyncio.sleep(0.1)

_led_blink_state = False

def _led_blink():
  if _led is None:
    return

  global _led_blink_state
  _led_blink_state = not _led_blink_state
  if _led_blink_state:
    _led[0] = (0, 4, 0)
  else:
    _led[0] = (4, 0, 0)

  _led.write()

async def task_various():
  wheel_speed_previous_motor_speed_erpm = 0
  charge_seen_ms = None
  global mode

  while True:
    # Calculate rear motor wheel speed
    if rear_motor.data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
      wheel_speed_previous_motor_speed_erpm = rear_motor.data.speed_erpm

      # 2*pi ≈ 6.28318
      perimeter = 6.28318 * rear_motor.data.cfg.wheel_radius  # meters
      motor_rpm = rear_motor.data.speed_erpm / max(1, rear_motor.data.cfg.poles_pair)
      rear_motor.data.wheel_speed = (perimeter * motor_rpm * 60.0) / 1000.0  # km/h

      # Small floor near zero to suppress standstill jitter while still showing 1 km/h.
      # No negative values
      if rear_motor.data.wheel_speed < 1.0:
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
  # Watchdog task_control_motor() feeds it continuously.
  wdt = WDT(timeout=30000)

  # Build the task list
  tasks = [
    asyncio.create_task(task_motors_refresh_data()),
    asyncio.create_task(task_control_motor_limit_current()),
    asyncio.create_task(task_control_motor(wdt)),
    asyncio.create_task(task_display_send_data()),
    asyncio.create_task(task_lights_send_data()),
    asyncio.create_task(task_espnow_receive_process_data()),
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
