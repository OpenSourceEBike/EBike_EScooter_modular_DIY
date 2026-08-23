import time
import gc
import uasyncio as asyncio

import common.config_runtime as cfg
from common.config_battery_resistance import (
  battery_resistance_config,
  validate_battery_resistance_measurement_config,
)
from common.battery_resistance import (
  BatteryResistanceEstimator,
)

from vars import Vars
from motor import MotorData, Motor
from brake import Brake
from throttle import Throttle
from common.utils import map_range
from common.espnow import espnow_init, ESPNowComms, espnow_recv_all, espnow_jittered_period_ms
from common.espnow_protocol import (
  BOARD_DISPLAY,
  BOARD_LIGHTS,
  BOARD_MOTOR,
  MSG_COMMAND,
  MSG_STATUS,
  HEALTH_MOTOR_LIGHTS_TX_OK,
  HEALTH_MOTOR_REAR_SPEED_VALID,
  build_command,
  build_status,
  parse_frame,
)
from common.lights_bits import REAR_BRAKE_BIT
from mode import Mode

TEMPERATURE_NOT_AVAILABLE_X10 = -2550
DISPLAY_MOTORS_ENABLE_TIMEOUT_MS = 2000
LIGHTS_TX_COMM_TIMEOUT_MS = 1500
LIGHTS_HEARTBEAT_MS = 250
LIGHTS_RETRY_MS = 50
LIGHTS_RETRY_MAX_MS = 1000
THROTTLE_REARM_ZERO_HOLD_MS = 1000
system_boot_ms = time.ticks_ms()
battery_resistance_config_error = validate_battery_resistance_measurement_config(
  battery_resistance_config)
CAN_LISP_FAST_TIMEOUT_MS = 1000
CAN_LISP_THERMAL_TIMEOUT_MS = 2000
# SOC is slow display telemetry, so retain the last valid value through
# transient CAN loss instead of publishing a misleading zero.
CAN_SOC_TIMEOUT_MS = 30000
if battery_resistance_config_error is not None:
  print("Battery resistance measurement disabled:",
        battery_resistance_config_error)
battery_resistance_estimator = (
  BatteryResistanceEstimator(battery_resistance_config, system_boot_ms)
  if battery_resistance_config_error is None else None
)

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
last_display_enable_command = False

# ESPNow wireless communications  
ESPNOW_DEBUG = bool(getattr(cfg, "espnow_debug", False))
sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_motor_board, debug=ESPNOW_DEBUG)

motor_board_tx_power = cfg.wifi_tx_power_dbm["motor_board"]
try:
  print("WiFi TX power before (motor_board): {} dBm".format(sta.config("txpower")))
except (AttributeError, OSError, ValueError):
  print("WiFi TX power before (motor_board): unavailable")
try:
  print("WiFi TX power config (motor_board): {} dBm".format(motor_board_tx_power))
  sta.config(txpower=motor_board_tx_power)
  print("WiFi TX power applied (motor_board): {} dBm".format(sta.config("txpower")))
except (AttributeError, OSError, ValueError):
  print("WiFi TX power configuration not supported (motor_board)")

try:
  sta.config(pm=sta.PM_NONE)
except (AttributeError, OSError, ValueError):
  pass

def decode_display_command(msg):
  parts = parse_frame(msg)
  if parts is None:
    return None
  if len(parts) == 7 and parts[0] == MSG_COMMAND and parts[1] == BOARD_DISPLAY and parts[2] == BOARD_MOTOR:
    return parts
  return None

def _can_timestamp_is_fresh(now, timestamp_ms,
                            timeout_ms=CAN_LISP_FAST_TIMEOUT_MS):
  return bool(
    timestamp_ms and
    0 <= time.ticks_diff(now, timestamp_ms) < timeout_ms
  )

def _rear_speed_is_fresh(now, motor_data):
  return _can_timestamp_is_fresh(
    now, motor_data.lisp_motion_last_update_ms, CAN_LISP_FAST_TIMEOUT_MS)

def _milliamps_to_current_x10(value):
  # Integer division of a negative value rounds down in Python, whereas CAN
  # status current values are truncated towards zero.
  return value // 100 if value >= 0 else -((-value) // 100)

def encode_display_status(vars, rear_motor_data, front_motor_data=None):
  brakes_are_active = 1 if vars.brakes_are_active else 0
  regen_braking_is_active = 1 if vars.regen_braking_is_active else 0
  cruise_control_is_active = 1 if vars.cruise_control.state == 2 else 0
  throttle_active = 1 if vars.throttle_value > 50 else 0
  throttle_right_fault = 1 if vars.throttle_right_fault else 0
  throttle_left_fault = 1 if vars.throttle_left_fault else 0

  motor_datas_local = [rear_motor_data]
  if front_motor_data is not None:
    motor_datas_local.append(front_motor_data)

  battery_current_x10 = sum(int(m.battery_current_x10) for m in motor_datas_local)
  motor_current_x10 = sum(int(m.motor_current_x10) for m in motor_datas_local)
  front_vesc_temperature_x10 = int(front_motor_data.vesc_temperature_x10) if front_motor_data is not None else TEMPERATURE_NOT_AVAILABLE_X10
  front_motor_temperature_x10 = int(front_motor_data.motor_temperature_x10) if front_motor_data is not None else TEMPERATURE_NOT_AVAILABLE_X10

  flags = ((brakes_are_active & 1) << 0) | \
          ((regen_braking_is_active & 1) << 1) | \
          ((1 if throttle_rearm_required else 0) << 2) | \
          ((vars.mode & 7) << 3) | \
          ((cruise_control_is_active & 1) << 6) | \
          ((throttle_active & 1) << 7) | \
          ((throttle_right_fault & 1) << 8) | \
          ((throttle_left_fault & 1) << 9)

  now = time.ticks_ms()
  health_bitmap = HEALTH_MOTOR_LIGHTS_TX_OK if vars.lights_comm_ok else 0
  if _rear_speed_is_fresh(now, rear_motor_data):
    health_bitmap |= HEALTH_MOTOR_REAR_SPEED_VALID

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
    int(vars.battery_resistance_mohm),
    int(vars.battery_resistance_debug_phase),
    int(vars.battery_resistance_debug_boot_seconds),
    int(vars.battery_resistance_debug_error_count),
    int(vars.battery_resistance_debug_sample_count),
    int(vars.battery_resistance_debug_reference_sample_count),
    int(vars.battery_resistance_debug_phase_elapsed_seconds),
    int(vars.lisp_motion_loss_count),
    int(vars.lisp_thermal_loss_count),
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
  debug=ESPNOW_DEBUG,
)

lights_tx_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_lights),
  encoder=encode_lights_message,
  debug=ESPNOW_DEBUG)

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
throttle_rearm_required = False
throttle_rearm_zero_since_ms = None

mode = Mode(brake_sensor, (throttle_1, throttle_2), vars, save_to_nvs=cfg.save_mode_to_nvs)

async def task_motors_refresh_data():
  period_ms = 50
  next_wake = time.ticks_ms()
  # Refresh latest VESC data (call once; it fills both via CAN)
  while True:
    if front_motor is None:
      rear_motor.update_motor_data(rear_motor, None)
    else:
      rear_motor.update_motor_data(rear_motor, front_motor)

    now = time.ticks_ms()
    for data in motor_data:
      # Each custom LISP family has its own cadence and expiry.
      if _can_timestamp_is_fresh(
          now, data.lisp_motion_last_update_ms, CAN_LISP_FAST_TIMEOUT_MS):
        data.speed_erpm = data.lisp_speed_erpm
        data.motor_current_x10 = data.lisp_motor_current_x10
      else:
        data.speed_erpm = 0
        data.wheel_speed = 0
        data.motor_current_x10 = 0

      if _can_timestamp_is_fresh(
          now, data.battery_precision_last_update_ms,
          CAN_LISP_FAST_TIMEOUT_MS):
        data.battery_voltage_x10 = (
          data.battery_voltage_measurement_x1000 // 100)
        data.battery_current_x10 = _milliamps_to_current_x10(
          data.battery_current_measurement_x1000)
      else:
        data.battery_current_x10 = 0
        data.battery_voltage_x10 = 0

      if _can_timestamp_is_fresh(
          now, data.lisp_thermal_last_update_ms, CAN_LISP_THERMAL_TIMEOUT_MS):
        data.vesc_temperature_x10 = data.lisp_vesc_temperature_x10
        data.motor_temperature_x10 = data.lisp_motor_temperature_x10
      else:
        data.vesc_temperature_x10 = 0
        data.motor_temperature_x10 = 0

      if _can_timestamp_is_fresh(
          now, data.lisp_thermal_last_update_ms, CAN_SOC_TIMEOUT_MS):
        data.battery_soc_x1000 = data.lisp_battery_soc_x1000
      else:
        data.battery_soc_x1000 = 0

    if battery_resistance_estimator is not None and not \
        battery_resistance_estimator.completed:
      resistance_mohm = battery_resistance_estimator.update(
        now, motor_data, vars.regen_braking_is_active)
      if resistance_mohm is not None:
        vars.battery_resistance_mohm = resistance_mohm
        print("Battery resistance measured: {} mOhm".format(
          resistance_mohm))

    vars.lisp_motion_loss_count = sum(
      data.lisp_motion_loss_count for data in motor_data)
    vars.lisp_thermal_loss_count = sum(
      data.lisp_thermal_loss_count for data in motor_data)

    if battery_resistance_estimator is not None:
      vars.battery_resistance_debug_phase = \
        battery_resistance_estimator.debug_phase
      vars.battery_resistance_debug_boot_seconds = \
        battery_resistance_estimator.debug_boot_qualifying_seconds
      vars.battery_resistance_debug_error_count = \
        battery_resistance_estimator.debug_error_count
      vars.battery_resistance_debug_sample_count = \
        battery_resistance_estimator.debug_sample_count
      vars.battery_resistance_debug_reference_sample_count = \
        battery_resistance_estimator.debug_reference_sample_count
      vars.battery_resistance_debug_phase_elapsed_seconds = \
        battery_resistance_estimator.debug_phase_elapsed_seconds
    else:
      vars.battery_resistance_debug_phase = -1
      vars.battery_resistance_debug_boot_seconds = 0
      vars.battery_resistance_debug_error_count = 0
      vars.battery_resistance_debug_sample_count = 0
      vars.battery_resistance_debug_reference_sample_count = 0
      vars.battery_resistance_debug_phase_elapsed_seconds = 0

    next_wake = time.ticks_add(next_wake, espnow_jittered_period_ms(period_ms))
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

async def task_display_send_data():
  period_ms = 100
  next_wake = time.ticks_ms()
  while True:
    if front_motor_data is None:
      vars.display_comm_ok = display_status_comms.send_data(vars, rear_motor_data)
    else:
      vars.display_comm_ok = display_status_comms.send_data(vars, rear_motor_data, front_motor_data)
    
    next_wake = time.ticks_add(
      next_wake, espnow_jittered_period_ms(period_ms)
    )
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def task_lights_send_data():
  period_ms = 50
  next_wake = time.ticks_ms()
  next_send_ms = time.ticks_ms()
  last_brake_bit = None
  last_tx_ok_ms = time.ticks_add(
    time.ticks_ms(), -LIGHTS_TX_COMM_TIMEOUT_MS
  )
  lights_retry_ms = LIGHTS_RETRY_MS
  while True:
    # A disabled motor state is also a hard lights-off command.  This keeps
    # the motor-board path consistent with the display-board light command.
    if (
      vars.motors_enable_state and
      (vars.brakes_are_active or vars.regen_braking_is_active)
    ):
      brake_bit = REAR_BRAKE_BIT
    else:
      brake_bit = 0

    now = time.ticks_ms()
    if (
      brake_bit != last_brake_bit or
      time.ticks_diff(now, next_send_ms) >= 0
    ):
      lights_ok = lights_tx_comms.send_data(REAR_BRAKE_BIT, brake_bit)
      if lights_ok:
        last_tx_ok_ms = now
        lights_retry_ms = LIGHTS_RETRY_MS
      else:
        lights_retry_ms = min(LIGHTS_RETRY_MAX_MS, lights_retry_ms * 2)
      last_brake_bit = brake_bit
      next_send_ms = time.ticks_add(
        now,
        espnow_jittered_period_ms(
          LIGHTS_HEARTBEAT_MS if lights_ok else lights_retry_ms
        ),
      )

    # A single lost radio frame is normal.  Report a failed link only after
    # several consecutive heartbeats have received no MAC-level response.
    vars.lights_comm_ok = time.ticks_diff(
      now, last_tx_ok_ms
    ) < LIGHTS_TX_COMM_TIMEOUT_MS

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

async def task_espnow_receive_process_data():
  global display_motors_enable_last_seen_ms, last_display_enable_command
  global throttle_rearm_required, throttle_rearm_zero_since_ms

  period_ms = 250
  next_wake = time.ticks_ms()
  while True:
    latest_packet = None
    for host, msg in espnow_recv_all(esp, debug=ESPNOW_DEBUG):
      parts = parse_frame(msg)
      if parts is None or len(parts) != 7:
        continue
      if parts[0] != MSG_COMMAND or parts[1] != BOARD_DISPLAY or parts[2] != BOARD_MOTOR:
        continue

      latest_packet = parts

    if latest_packet is not None:
      parts = latest_packet
      vars.display_comm_ok = True
      new_enable_state = bool(parts[3])
      if new_enable_state and not last_display_enable_command:
        throttle_rearm_required = True
        throttle_rearm_zero_since_ms = None
      elif not new_enable_state:
        throttle_rearm_required = False
        throttle_rearm_zero_since_ms = None
      last_display_enable_command = new_enable_state
      vars.motors_enable_state = new_enable_state
      display_motors_enable_last_seen_ms = time.ticks_ms()
      vars.buttons_state = parts[4]
      vars.turn_off_relay = bool(parts[6])

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

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

async def task_control_motor():
  global throttle_1_disabled, throttle_2_disabled, throttle_rearm_required
  global throttle_rearm_zero_since_ms
  global display_motors_enable_last_seen_ms, last_display_enable_command
  _release_condition_since_ms = None

  # Hall-effect throttle supply can spike above over-max threshold at power-on;
  # a single bad reading permanently sets throttle_1_disabled with no recovery path.
  await asyncio.sleep_ms(500)
  period_ms = 20
  next_wake = time.ticks_ms()

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

    # Re-arm protection: after every disabled -> enabled transition, the
    # rider must release the throttle to the existing zero/deadband before
    # any motor target can be applied.
    if not vars.motors_enable_state:
      throttle_rearm_required = False
      throttle_rearm_zero_since_ms = None
    elif throttle_rearm_required:
      now = time.ticks_ms()
      if throttle_value <= Mode.THROTTLE_ZERO_MAX:
        if throttle_rearm_zero_since_ms is None:
          throttle_rearm_zero_since_ms = now
        elif time.ticks_diff(now, throttle_rearm_zero_since_ms) >= THROTTLE_REARM_ZERO_HOLD_MS:
          throttle_rearm_required = False
          throttle_rearm_zero_since_ms = None
      else:
        # The one-second zero-throttle window must be continuous.
        throttle_rearm_zero_since_ms = None

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

    # Brakes
    vars.brakes_are_active = True if brake_sensor.value else False

    # Fail safe: if the display stops refreshing the enable command, drop to
    # disabled state after the normal communication timeout.
    if (
      vars.motors_enable_state and
      display_motors_enable_last_seen_ms is not None and
      time.ticks_diff(time.ticks_ms(), display_motors_enable_last_seen_ms) >= DISPLAY_MOTORS_ENABLE_TIMEOUT_MS
    ):
        vars.motors_enable_state = False
        last_display_enable_command = False
        throttle_rearm_required = False
        throttle_rearm_zero_since_ms = None
        vars.display_comm_ok = False

    # Consider less then 10 negative amps of motor current for regen_brakes_are_active = True
    motor_current = sum(motor.data.motor_current_x10 for motor in motors) // 10
    vars.regen_braking_is_active = True if motor_current < -10 else False

    # Command motor(s)
    if vars.motors_enable_state is False or throttle_rearm_required:
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

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

async def task_control_motor_limit_current():
  period_ms = 100
  next_wake = time.ticks_ms()
  while True:
    # The limits are speed-dependent, so do not turn a short command-102 gap
    # into a false 0 km/h reading. task_motors_refresh_data() still expires
    # the operational speed for status/UI safety, but the VESC retains the
    # last limits sent here until a fresh rear speed is available again.
    #
    # Recomputing with zero would temporarily select the standstill limits
    # (notably a much higher rear motor-current limit) and can cause a
    # noticeable torque spike while the scooter is moving.
    now = time.ticks_ms()
    rear_speed_is_fresh = _rear_speed_is_fresh(now, rear_motor.data)
    if not rear_speed_is_fresh:
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      await asyncio.sleep_ms(remaining if remaining > 0 else 0)
      continue

    # Always use a fresh rear wheel speed.
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

    # Limit updates do not belong in the 20 ms actuation loop. The VESC keeps
    # the latest limits, so refresh them here at this task's 100 ms cadence.
    for motor in motors:
      motor.set_motor_current_limits(
        motor.data.motor_target_current_limit_min,
        motor.data.motor_target_current_limit_max)
      motor.set_battery_current_limits(
        motor.data.battery_target_current_limit_min,
        motor.data.battery_target_current_limit_max)

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

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
  period_ms = 100
  next_wake = time.ticks_ms()
  wheel_speed_previous_motor_speed_erpm = 0
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

    # Run Mode tick
    mode.tick()

    _led_blink()

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

async def task_gc_maintenance():
  """Keep full garbage collections out of the control and communications paths.

  ``gc.collect()`` stops this cooperative scheduler while it runs.  Calling it
  from the 20 ms motor-control loop (or from CAN/ESP-NOW tasks) therefore adds
  unpredictable latency to motor commands and safety-state propagation.

  Let MicroPython's automatic GC handle allocation pressure normally, while
  this low-priority task reclaims memory proactively only when free heap falls
  below a conservative reserve.  The reserve is 20% of the free heap measured
  just after startup, never less than 8 KiB.  A two-second check interval keeps
  the collection rate low without waiting for allocation failure.
  """
  # Establish the reference after all board objects and asyncio tasks exist.
  # The initial collection runs once during startup, outside time-critical work.
  gc.collect()
  baseline_free_bytes = gc.mem_free()
  low_watermark_bytes = max(8192, baseline_free_bytes // 5)

  period_ms = 2000
  next_wake = time.ticks_ms()
  while True:
    # Do not force a complete collection on every check: if the reserve remains
    # available, avoid a scheduler pause and leave the heap untouched.
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)
    if gc.mem_free() < low_watermark_bytes:
      gc.collect()

async def main():
  # Build the task list
  tasks = [
    asyncio.create_task(task_motors_refresh_data()),
    asyncio.create_task(task_control_motor_limit_current()),
    asyncio.create_task(task_control_motor()),
    asyncio.create_task(task_display_send_data()),
    asyncio.create_task(task_lights_send_data()),
    asyncio.create_task(task_espnow_receive_process_data()),
    asyncio.create_task(task_various()),
    asyncio.create_task(task_gc_maintenance()),
  ]

  print("Starting EBike/EScooter\n")

  # Wait for all tasks (keeps main alive; propagates exceptions)
  await asyncio.gather(*tasks)

asyncio.run(main())
