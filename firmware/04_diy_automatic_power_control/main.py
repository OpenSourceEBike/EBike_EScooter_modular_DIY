import time
import gc
from machine import Pin, I2C, deepsleep
import esp32

from common.espnow import espnow_init, ESPNowComms
from common.espnow_protocol import (
  BOARD_DISPLAY,
  BOARD_MOTOR,
  BOARD_POWER_SWITCH,
  MSG_COMMAND,
  MSG_STATUS,
  POWER_CONFIG_CMD,
  POWER_SWITCH_CMD,
  parse_frame,
)
import common.config_runtime as cfg
from adxl345 import ADXL345

################################################################
# CONFIGURATIONS

debug_enable = False

################################################################

# Relay control pins on the ESP32-S2 power board.
# Assert them as early as possible so display power comes up before radio,
# I2C and accelerometer initialization.
SWITCH_PINS_NUMBERS = (18, 33, 35, 37, 39)
switch_pins = [Pin(p, Pin.OUT, value=1) for p in SWITCH_PINS_NUMBERS]

if debug_enable:
  print("Starting the DIY Automatic Anti Spark Switch")
  print("EBike/EScooter type: " + cfg.type_name)
  print()

vehicle_type = cfg.type.get("ebike_escooter") if isinstance(cfg.type, dict) else None
if vehicle_type not in (cfg.TYPE_EBIKE, cfg.TYPE_ESCOOTER):
  raise ValueError("You need to select a valid EBike/EScooter type")

power_timeout_seconds_to_disable_relay = int(
  cfg.timeout_no_motion_seconds_to_disable_relay
)
power_seconds_to_wait_before_sleep = int(
  getattr(cfg, "seconds_to_wait_before_movement_detection", 20)
)

NVS_NAMESPACE = "diy_power_sw"
NVS_KEY_THRESHOLD = "motion_thr"
NVS_KEY_RATE_HZ = "motion_rate"
NVS_KEY_AC_MODE = "motion_ac"
NVS_KEY_TIMEOUT_SECONDS = "timeout_sec"
NVS_KEY_WAIT_SECONDS = "wait_sec"
DEFAULT_POWER_THRESHOLD = cfg.motion_detection_threshold
DEFAULT_POWER_RATE_HZ = cfg.motion_detection_rate_hz
DEFAULT_POWER_AC_MODE = bool(getattr(cfg, "motion_detection_ac_mode", True))
DEFAULT_TIMEOUT_SECONDS = power_timeout_seconds_to_disable_relay
DEFAULT_WAIT_SECONDS = power_seconds_to_wait_before_sleep

turn_off_relay = False
power_threshold = DEFAULT_POWER_THRESHOLD
power_rate_hz = DEFAULT_POWER_RATE_HZ
power_ac_mode = DEFAULT_POWER_AC_MODE
power_timeout_seconds_to_disable_relay = DEFAULT_TIMEOUT_SECONDS
power_seconds_to_wait_before_sleep = DEFAULT_WAIT_SECONDS

def _open_nvs():
  try:
    return esp32.NVS(NVS_NAMESPACE)
  except Exception:
    return None

def _validate_power_settings(threshold, rate_hz):
  try:
    validated_threshold = ADXL345.normalize_motion_threshold(threshold)
    validated_rate_hz = ADXL345.normalize_motion_rate_hz(rate_hz)
  except Exception:
    return None
  return validated_threshold, validated_rate_hz

def _validate_power_ac_mode(ac_mode):
  try:
    ac_mode = int(ac_mode)
    if ac_mode not in (0, 1):
      return None
    return bool(ac_mode)
  except Exception:
    return None

def _validate_positive_seconds(value, max_seconds=3600):
  try:
    value = int(value)
    if value <= 0 or value > max_seconds:
      return None
    return value
  except Exception:
    return None

def load_power_settings_from_nvs():
  nvs = _open_nvs()
  if nvs is None:
    return (
      DEFAULT_POWER_THRESHOLD,
      DEFAULT_POWER_RATE_HZ,
      DEFAULT_POWER_AC_MODE,
      DEFAULT_TIMEOUT_SECONDS,
      DEFAULT_WAIT_SECONDS,
    )

  try:
    stored_threshold = nvs.get_i32(NVS_KEY_THRESHOLD)
    stored_rate_hz = nvs.get_i32(NVS_KEY_RATE_HZ)
    stored_ac_mode = nvs.get_i32(NVS_KEY_AC_MODE)
    stored_timeout_seconds = nvs.get_i32(NVS_KEY_TIMEOUT_SECONDS)
    stored_wait_seconds = nvs.get_i32(NVS_KEY_WAIT_SECONDS)
  except Exception:
    return (
      DEFAULT_POWER_THRESHOLD,
      DEFAULT_POWER_RATE_HZ,
      DEFAULT_POWER_AC_MODE,
      DEFAULT_TIMEOUT_SECONDS,
      DEFAULT_WAIT_SECONDS,
    )

  validated = _validate_power_settings(stored_threshold, stored_rate_hz)
  validated_ac_mode = _validate_power_ac_mode(stored_ac_mode)
  validated_timeout_seconds = _validate_positive_seconds(stored_timeout_seconds)
  validated_wait_seconds = _validate_positive_seconds(stored_wait_seconds)
  if (
    validated is None or
    validated_ac_mode is None or
    validated_timeout_seconds is None or
    validated_wait_seconds is None
  ):
    return (
      DEFAULT_POWER_THRESHOLD,
      DEFAULT_POWER_RATE_HZ,
      DEFAULT_POWER_AC_MODE,
      DEFAULT_TIMEOUT_SECONDS,
      DEFAULT_WAIT_SECONDS,
    )

  return (
    validated[0],
    validated[1],
    validated_ac_mode,
    validated_timeout_seconds,
    validated_wait_seconds,
  )

def save_power_settings_to_nvs(threshold, rate_hz, ac_mode, timeout_seconds, wait_seconds):
  validated = _validate_power_settings(threshold, rate_hz)
  validated_ac_mode = _validate_power_ac_mode(ac_mode)
  validated_timeout_seconds = _validate_positive_seconds(timeout_seconds)
  validated_wait_seconds = _validate_positive_seconds(wait_seconds)
  if (
    validated is None or
    validated_ac_mode is None or
    validated_timeout_seconds is None or
    validated_wait_seconds is None
  ):
    return False

  validated_threshold, validated_rate_hz = validated
  nvs = _open_nvs()
  if nvs is None:
    return False

  try:
    nvs.set_i32(NVS_KEY_THRESHOLD, validated_threshold)
    nvs.set_i32(NVS_KEY_RATE_HZ, validated_rate_hz)
    nvs.set_i32(NVS_KEY_AC_MODE, 1 if validated_ac_mode else 0)
    nvs.set_i32(NVS_KEY_TIMEOUT_SECONDS, validated_timeout_seconds)
    nvs.set_i32(NVS_KEY_WAIT_SECONDS, validated_wait_seconds)
    nvs.commit()
  except Exception:
    return False

  return True

# ESPNow wireless communications
ESPNOW_DEBUG = bool(getattr(cfg, "espnow_debug", False))
_sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_power_switch, debug=ESPNOW_DEBUG)

def decode_power_switch_message(msg):
  parts = parse_frame(msg)
  if parts is None:
    return None
  if parts[0] != MSG_COMMAND or parts[2] != BOARD_POWER_SWITCH or parts[1] not in (BOARD_DISPLAY, BOARD_MOTOR):
    return None
  if len(parts) == 5 and parts[3] == POWER_SWITCH_CMD:
    return parts
  if len(parts) == 9 and parts[3] == POWER_CONFIG_CMD:
    return parts
  return None

_POWER_SETTINGS_ECHO_REPEATS = 10
_POWER_SETTINGS_ECHO_DELAY_MS = 250
_pending_power_settings_echo_host = None
_pending_power_settings_echo_dst_id = None
_pending_power_settings_echo_payload = None
_pending_power_settings_echo_count = 0
_pending_power_settings_echo_next_ms = 0

def _queue_power_settings_echo(host, dst_id):
  global _pending_power_settings_echo_host
  global _pending_power_settings_echo_dst_id
  global _pending_power_settings_echo_payload
  global _pending_power_settings_echo_count
  global _pending_power_settings_echo_next_ms

  if host is None:
    return

  try:
    esp.add_peer(host)
  except OSError:
    pass
  except Exception as ex:
    if ESPNOW_DEBUG:
      print("ESP-NOW add_peer error:", ex)

  _pending_power_settings_echo_host = host
  _pending_power_settings_echo_dst_id = dst_id
  _pending_power_settings_echo_payload = " ".join((
    str(int(MSG_STATUS)),
    str(int(BOARD_POWER_SWITCH)),
    str(int(dst_id)),
    str(0),
    str(int(power_threshold)),
    str(int(power_rate_hz)),
    str(1 if power_ac_mode else 0),
    str(int(power_timeout_seconds_to_disable_relay)),
    str(int(power_seconds_to_wait_before_sleep)),
  )).encode("ascii")
  _pending_power_settings_echo_count = _POWER_SETTINGS_ECHO_REPEATS
  _pending_power_settings_echo_next_ms = time.ticks_ms()

def _process_pending_power_settings_echo():
  global _pending_power_settings_echo_count
  global _pending_power_settings_echo_next_ms

  if _pending_power_settings_echo_count <= 0:
    return
  if time.ticks_diff(time.ticks_ms(), _pending_power_settings_echo_next_ms) < 0:
    return

  host = _pending_power_settings_echo_host
  payload = _pending_power_settings_echo_payload
  if host is None or payload is None:
    _pending_power_settings_echo_count = 0
    return

  try:
    esp.send(host, payload)
  except OSError as ex:
    if not (ex.args and ex.args[0] == 116):
      if ESPNOW_DEBUG:
        print("ESP-NOW tx error:", ex)
  except Exception as ex:
    if ESPNOW_DEBUG:
      print("ESP-NOW tx error:", ex)

  _pending_power_settings_echo_count -= 1
  if _pending_power_settings_echo_count > 0:
    _pending_power_settings_echo_next_ms = time.ticks_add(
      time.ticks_ms(),
      _POWER_SETTINGS_ECHO_DELAY_MS,
    )

espnow_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_motor_board),
  decoder=decode_power_switch_message,
  debug=ESPNOW_DEBUG,
)

# ADXL345 pins (adjust if needed)
ADXL_SCL_PIN = 1
ADXL_SDA_PIN = 2
ADXL_INT_PIN = 8

i2c = I2C(0, scl=Pin(ADXL_SCL_PIN), sda=Pin(ADXL_SDA_PIN), freq=400_000)
found_addrs = i2c.scan()
if ADXL345._ADDR in found_addrs:
  adxl_addr = ADXL345._ADDR
elif ADXL345._ADDR_ALT in found_addrs:
  adxl_addr = ADXL345._ADDR_ALT
else:
  raise RuntimeError(
    "ADXL345 not found on I2C. Check wiring/power or address. "
    f"Scanned: {[hex(a) for a in found_addrs]}"
  )

power_threshold, power_rate_hz, power_ac_mode, power_timeout_seconds_to_disable_relay, power_seconds_to_wait_before_sleep = load_power_settings_from_nvs()
validated_defaults = _validate_power_settings(power_threshold, power_rate_hz)
validated_default_ac_mode = _validate_power_ac_mode(power_ac_mode)
validated_default_timeout_seconds = _validate_positive_seconds(power_timeout_seconds_to_disable_relay)
validated_default_wait_seconds = _validate_positive_seconds(power_seconds_to_wait_before_sleep)
if (
  validated_defaults is None or
  validated_default_ac_mode is None or
  validated_default_timeout_seconds is None or
  validated_default_wait_seconds is None
):
  power_threshold = DEFAULT_POWER_THRESHOLD
  power_rate_hz = DEFAULT_POWER_RATE_HZ
  power_ac_mode = DEFAULT_POWER_AC_MODE
  power_timeout_seconds_to_disable_relay = DEFAULT_TIMEOUT_SECONDS
  power_seconds_to_wait_before_sleep = DEFAULT_WAIT_SECONDS
else:
  power_threshold, power_rate_hz = validated_defaults
  power_ac_mode = validated_default_ac_mode
  power_timeout_seconds_to_disable_relay = validated_default_timeout_seconds
  power_seconds_to_wait_before_sleep = validated_default_wait_seconds
save_power_settings_to_nvs(
  power_threshold,
  power_rate_hz,
  power_ac_mode,
  power_timeout_seconds_to_disable_relay,
  power_seconds_to_wait_before_sleep,
)

accelerometer = ADXL345(i2c, ADXL_INT_PIN, address=adxl_addr)
accelerometer.setup_motion_detection(
  threshold=power_threshold,
  rate_hz=power_rate_hz,
  ac_mode=power_ac_mode,
)
accelerometer.events.get("motion")

last_time_motion_detected = time.ticks_ms()
power_timeout_deadline = time.ticks_add(
  last_time_motion_detected, power_timeout_seconds_to_disable_relay * 1000
)

if debug_enable:
  motion_counter = 0
  timeout_counter_previous = 0

# A full collection pauses this loop, which is responsible for ESP-NOW relay
# commands and motion processing.  Let MicroPython collect automatically under
# allocation pressure and run a proactive collection only if free heap drops
# below a reserve of 20% of the post-startup value (at least 8 KiB).
GC_MAINTENANCE_INTERVAL_MS = 2000
gc.collect()
gc_baseline_free_bytes = gc.mem_free()
gc_low_watermark_bytes = max(8192, gc_baseline_free_bytes // 5)
next_gc_maintenance_ms = time.ticks_add(
  time.ticks_ms(), GC_MAINTENANCE_INTERVAL_MS
)

period_ms = 20
next_wake = time.ticks_ms()

while True:

  # process any data received by ESPNow
  packet = espnow_comms.get_latest_data_with_host()
  if packet is None:
    host = None
    msg = None
  else:
    host, msg = packet
  if msg is not None and len(msg) >= 5:
    command_id, src_id, dst_id, power_cmd = msg[0], msg[1], msg[2], msg[3]
    if command_id == MSG_COMMAND:
      if power_cmd == POWER_SWITCH_CMD and len(msg) == 5:
        turn_off_relay = True if int(msg[4]) != 0 else False
      elif power_cmd == POWER_CONFIG_CMD and len(msg) == 9:
        threshold, rate_hz, ac_mode, timeout_seconds, wait_seconds = msg[4], msg[5], msg[6], msg[7], msg[8]
        validated = _validate_power_settings(threshold, rate_hz)
        validated_ac_mode = _validate_power_ac_mode(ac_mode)
        validated_timeout_seconds = _validate_positive_seconds(timeout_seconds)
        validated_wait_seconds = _validate_positive_seconds(wait_seconds)
        if validated is not None:
          new_power_threshold, new_power_rate_hz = validated
        else:
          new_power_threshold = power_threshold
          new_power_rate_hz = power_rate_hz
        if validated_ac_mode is not None:
          new_power_ac_mode = validated_ac_mode
        else:
          new_power_ac_mode = power_ac_mode
        if validated_timeout_seconds is not None:
          new_power_timeout_seconds_to_disable_relay = validated_timeout_seconds
        else:
          new_power_timeout_seconds_to_disable_relay = power_timeout_seconds_to_disable_relay
        if validated_wait_seconds is not None:
          new_power_seconds_to_wait_before_sleep = validated_wait_seconds
        else:
          new_power_seconds_to_wait_before_sleep = power_seconds_to_wait_before_sleep

        if (
          new_power_threshold != power_threshold or
          new_power_rate_hz != power_rate_hz or
          new_power_ac_mode != power_ac_mode or
          new_power_timeout_seconds_to_disable_relay != power_timeout_seconds_to_disable_relay or
          new_power_seconds_to_wait_before_sleep != power_seconds_to_wait_before_sleep
        ):
          power_threshold = new_power_threshold
          power_rate_hz = new_power_rate_hz
          power_ac_mode = new_power_ac_mode
          power_timeout_seconds_to_disable_relay = new_power_timeout_seconds_to_disable_relay
          power_seconds_to_wait_before_sleep = new_power_seconds_to_wait_before_sleep
          accelerometer.setup_motion_detection(
            threshold=power_threshold,
            rate_hz=power_rate_hz,
            ac_mode=power_ac_mode,
          )
          save_power_settings_to_nvs(
            power_threshold,
            power_rate_hz,
            power_ac_mode,
            power_timeout_seconds_to_disable_relay,
            power_seconds_to_wait_before_sleep,
          )
          power_timeout_deadline = time.ticks_add(
            time.ticks_ms(),
            power_timeout_seconds_to_disable_relay * 1000,
          )
          _queue_power_settings_echo(host, src_id)

  _process_pending_power_settings_echo()

  # save time value when motion is detected
  if accelerometer.events.get("motion"):
    last_time_motion_detected = time.ticks_ms()
    power_timeout_deadline = time.ticks_add(
      last_time_motion_detected,
      power_timeout_seconds_to_disable_relay * 1000,
    )

    if debug_enable:
      motion_counter += 1
      print(f"Motion counter: {motion_counter}")

  # if we should turn off the relay, leave this infinite loop
  if turn_off_relay:
    if debug_enable:
      print("Turn off relay command")
      
    break

  # if timeout, leave this infinite loop
  if time.ticks_diff(time.ticks_ms(), power_timeout_deadline) >= 0:
    break

  if debug_enable:
    remaining_ms = time.ticks_diff(power_timeout_deadline, time.ticks_ms())
    if remaining_ms < 0:
      remaining_ms = 0
    timeout_counter = remaining_ms // 1000
    if timeout_counter != timeout_counter_previous:
      timeout_counter_previous = timeout_counter
      print(f"Timeout remaining seconds: {timeout_counter}")

  # Avoid a complete GC pause in every ~20 ms iteration.  Check infrequently
  # and collect only when memory has crossed the configured reserve.
  now = time.ticks_ms()
  if time.ticks_diff(now, next_gc_maintenance_ms) >= 0:
    next_gc_maintenance_ms = time.ticks_add(now, GC_MAINTENANCE_INTERVAL_MS)
    if gc.mem_free() < gc_low_watermark_bytes:
      gc.collect()

  next_wake = time.ticks_add(next_wake, period_ms)
  remaining = time.ticks_diff(next_wake, time.ticks_ms())
  time.sleep_ms(remaining if remaining > 0 else 0)


if debug_enable:
  print(f"Prepare to enter in sleep mode - delay of {power_seconds_to_wait_before_sleep} seconds")

# if we are here, we should turn off the relay
for pin in switch_pins:
  pin.value(0)

# wait some time before next movement detection
time.sleep(power_seconds_to_wait_before_sleep)

# Clear any motion interrupt latched during the wait before arming wake.
accelerometer.events.get("motion")

esp32.wake_on_ext0(pin=Pin(ADXL_INT_PIN, Pin.IN), level=1)

if debug_enable:
  print("Enter in sleep mode")

deepsleep()
