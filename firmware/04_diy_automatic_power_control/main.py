import time
import gc
from machine import Pin, I2C, deepsleep
import esp32

from common.espnow import espnow_init, ESPNowComms
from common.espnow_commands import COMMAND_ID_POWER_SWITCH_1
import common.config_runtime as cfg
from adxl345 import ADXL345

################################################################
# CONFIGURATIONS

timeout_no_motion_minutes_to_disable_relay = 5  # 5 minutes seems a good value
seconds_to_wait_before_movement_detection = 20  # 20 seconds seems a good value

debug_enable = False

################################################################

# Relay control pins (C3)
# Assert them as early as possible in main.py so display power comes up before
# radio, I2C and accelerometer initialization.
SWITCH_PINS_NUMBERS = (0, 1, 2, 3, 4)
switch_pins = [Pin(p, Pin.OUT, value=1) for p in SWITCH_PINS_NUMBERS]

if debug_enable:
  print("Starting the DIY Automatic Anti Spark Switch")
  print("EBike/EScooter type: " + cfg.type_name)
  print()

vehicle_type = cfg.type.get("ebike_escooter") if isinstance(cfg.type, dict) else None
if vehicle_type not in (cfg.TYPE_EBIKE, cfg.TYPE_ESCOOTER):
  raise ValueError("You need to select a valid EBike/EScooter type")

timeout_no_motion_minutes_to_disable_relay *= 60  # need to multiply by 60 seconds
timeout_no_motion_ms = timeout_no_motion_minutes_to_disable_relay * 1000

NVS_NAMESPACE = "diy_power_sw"
NVS_KEY_THRESHOLD = "motion_thr"
NVS_KEY_RATE_HZ = "motion_rate"
DEFAULT_MOTION_THRESHOLD = cfg.motion_detection_threshold
DEFAULT_MOTION_RATE_HZ = cfg.motion_detection_rate_hz

turn_off_relay = False
motion_threshold = DEFAULT_MOTION_THRESHOLD
motion_rate_hz = DEFAULT_MOTION_RATE_HZ

def _open_nvs():
  try:
    return esp32.NVS(NVS_NAMESPACE)
  except Exception:
    return None

def _validate_motion_settings(threshold, rate_hz):
  try:
    validated_threshold = ADXL345.normalize_motion_threshold(threshold)
    validated_rate_hz = ADXL345.normalize_motion_rate_hz(rate_hz)
  except Exception:
    return None
  return validated_threshold, validated_rate_hz

def load_motion_settings_from_nvs():
  nvs = _open_nvs()
  if nvs is None:
    return DEFAULT_MOTION_THRESHOLD, DEFAULT_MOTION_RATE_HZ

  try:
    stored_threshold = nvs.get_i32(NVS_KEY_THRESHOLD)
    stored_rate_hz = nvs.get_i32(NVS_KEY_RATE_HZ)
  except Exception:
    return DEFAULT_MOTION_THRESHOLD, DEFAULT_MOTION_RATE_HZ

  validated = _validate_motion_settings(stored_threshold, stored_rate_hz)
  if validated is None:
    return DEFAULT_MOTION_THRESHOLD, DEFAULT_MOTION_RATE_HZ

  return validated

def save_motion_settings_to_nvs(threshold, rate_hz):
  validated = _validate_motion_settings(threshold, rate_hz)
  if validated is None:
    return False

  validated_threshold, validated_rate_hz = validated
  nvs = _open_nvs()
  if nvs is None:
    return False

  try:
    nvs.set_i32(NVS_KEY_THRESHOLD, validated_threshold)
    nvs.set_i32(NVS_KEY_RATE_HZ, validated_rate_hz)
    nvs.commit()
  except Exception:
    return False

  return True

# ESPNow wireless communications
_sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_power_switch)

def decode_power_switch_message(msg):
  parts = [int(s) for s in msg.decode("ascii").split()]
  if len(parts) == 4 and parts[0] == COMMAND_ID_POWER_SWITCH_1:
    return parts
  return None

espnow_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_display),
  decoder=decode_power_switch_message,
)

# ADXL345 pins (adjust if needed)
ADXL_SCL_PIN = 20
ADXL_SDA_PIN = 21
ADXL_INT_PIN = 10

i2c = I2C(0, scl=Pin(ADXL_SCL_PIN), sda=Pin(ADXL_SDA_PIN), freq=400_000)
found_addrs = i2c.scan()
if ADXL345._ADDR not in found_addrs:
  raise RuntimeError(
    "ADXL345 not found on I2C. Check wiring/power or address. "
    f"Scanned: {[hex(a) for a in found_addrs]}"
  )

motion_threshold, motion_rate_hz = load_motion_settings_from_nvs()
validated_defaults = _validate_motion_settings(motion_threshold, motion_rate_hz)
if validated_defaults is None:
  motion_threshold = DEFAULT_MOTION_THRESHOLD
  motion_rate_hz = DEFAULT_MOTION_RATE_HZ
else:
  motion_threshold, motion_rate_hz = validated_defaults
save_motion_settings_to_nvs(motion_threshold, motion_rate_hz)

accelerometer = ADXL345(i2c, ADXL_INT_PIN)
accelerometer.setup_motion_detection(
  threshold=motion_threshold,
  rate_hz=motion_rate_hz,
)

last_time_motion_detected = time.ticks_ms()
motion_timeout_deadline = time.ticks_add(
  last_time_motion_detected, timeout_no_motion_ms
)

if debug_enable:
  motion_counter = 0
  timeout_counter_previous = 0

while True:

  # process any data received by ESPNow
  msg = espnow_comms.get_data()
  if msg is not None and len(msg) == 4:
    command_id, turn_off, threshold, rate_hz = msg
    if command_id == COMMAND_ID_POWER_SWITCH_1:
      turn_off_relay = True if int(turn_off) != 0 else False
      validated = _validate_motion_settings(threshold, rate_hz)
      if validated is not None:
        new_motion_threshold, new_motion_rate_hz = validated
      else:
        new_motion_threshold = motion_threshold
        new_motion_rate_hz = motion_rate_hz

      if (
        new_motion_threshold != motion_threshold or
        new_motion_rate_hz != motion_rate_hz
      ):
        motion_threshold = new_motion_threshold
        motion_rate_hz = new_motion_rate_hz
        accelerometer.setup_motion_detection(
          threshold=motion_threshold,
          rate_hz=motion_rate_hz,
        )
        save_motion_settings_to_nvs(motion_threshold, motion_rate_hz)

  # save time value when motion is detected
  if accelerometer.motion_detected():
    last_time_motion_detected = time.ticks_ms()
    motion_timeout_deadline = time.ticks_add(
      last_time_motion_detected, timeout_no_motion_ms
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
  if time.ticks_diff(time.ticks_ms(), motion_timeout_deadline) >= 0:
    break

  if debug_enable:
    remaining_ms = time.ticks_diff(motion_timeout_deadline, time.ticks_ms())
    if remaining_ms < 0:
      remaining_ms = 0
    timeout_counter = remaining_ms // 1000
    if timeout_counter != timeout_counter_previous:
      timeout_counter_previous = timeout_counter
      print(f"Timeout remaining seconds: {timeout_counter}")

  # do memory clean
  gc.collect()

  # sleep some very little time
  time.sleep(0.02)


if debug_enable:
  print(f"Prepare to enter in sleep mode - delay of {seconds_to_wait_before_movement_detection} seconds")

# if we are here, we should turn off the relay
for pin in switch_pins:
  pin.value(0)

# wait some time before next movement detection
time.sleep(seconds_to_wait_before_movement_detection)

esp32.wake_on_ext0(pin=Pin(ADXL_INT_PIN, Pin.IN), level=1)

if debug_enable:
  print("Enter in sleep mode")

deepsleep()
