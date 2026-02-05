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

debug_enable = True

################################################################

if debug_enable:
  print("Starting the DIY Automatic Anti Spark Switch")
  print("EBike/EScooter type: " + cfg.type_name)
  print()

vehicle_type = cfg.type.get("ebike_escooter") if isinstance(cfg.type, dict) else None
if vehicle_type not in (cfg.TYPE_EBIKE, cfg.TYPE_ESCOOTER):
  raise ValueError("You need to select a valid EBike/EScooter type")

# Relay control pins (C3)
SWITCH_PINS_NUMBERS = (0, 1, 2, 3, 4)
switch_pins = [Pin(p, Pin.OUT, value=1) for p in SWITCH_PINS_NUMBERS]

timeout_no_motion_minutes_to_disable_relay *= 60  # need to multiply by 60 seconds
timeout_no_motion_ms = timeout_no_motion_minutes_to_disable_relay * 1000

turn_off_relay = False

# ESPNow wireless communications
_sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_power_switch)

def decode_power_switch_message(msg):
  parts = [int(s) for s in msg.decode("ascii").split()]
  if len(parts) == 2 and parts[0] == COMMAND_ID_POWER_SWITCH_1:
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
accelerometer = ADXL345(i2c, ADXL_INT_PIN)
accelerometer.setup_motion_detection(threshold=16)

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
  if msg is not None and len(msg) == 2:
    command_id, turn_off = msg
    if command_id == COMMAND_ID_POWER_SWITCH_1:
      turn_off_relay = True if int(turn_off) != 0 else False

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
      print(f"Timeout remaining seconds: {timeout_no_motion_minutes_to_disable_relay - timeout_counter}")

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
