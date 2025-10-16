import board
import digitalio

import supervisor
supervisor.runtime.autoreload = False

# enable the IO pins to control the switch
# needs a few pins as the relay uses some good amount of current
switch_pins_numbers = [board.IO18, board.IO33, board.IO35, board.IO37, board.IO39]
switch_pins = [0] * len(switch_pins_numbers)

# configure the pins as outputs and enable
for index, switch_pin_number in enumerate(switch_pins_numbers):
  switch_pins[index] = digitalio.DigitalInOut(switch_pin_number)
  switch_pins[index].direction = digitalio.Direction.OUTPUT
  switch_pins[index].value = True

import busio
import adafruit_adxl34x
import alarm
import time
import gc
import wifi
import espnow
import espnow_comms as _ESPNowComms
import system_data as _SystemData

################################################################
# CONFIGURATIONS

timeout_no_motion_minutes_to_disable_relay = 5 # 5 minutes seems a good value

seconds_to_wait_before_movement_detection = 20 # 20 seconds seems a good value

my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf1]

debug_enable = True

################################################################

timeout_no_motion_minutes_to_disable_relay *= 60 # need to multiply by 60 seconds

if debug_enable:
  print("Starting the DIY Automatic Anti Spark Switch")

# if we are here, is because
# the system just wake up from deep sleep,
# due to motion detection

system_data = _SystemData.SystemData()

# set mac address
# this is also need to start ESPNow
wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

_espnow = espnow.ESPNow()
espnow_comms = _ESPNowComms.ESPNowComms(_espnow, system_data)

# pins used by the ADXL345
scl_pin = board.IO1
sda_pin = board.IO2
int1_pin = board.IO8

# init the ADXL345
i2c = busio.I2C(scl_pin, sda_pin)
accelerometer = adafruit_adxl34x.ADXL345(i2c)
accelerometer.enable_motion_detection(threshold = 16) # 16 seems to be the min value possible
accelerometer.events.get('motion') # this will clear the interrupt

last_time_motion_detected = time.monotonic()

if debug_enable:
  motion_counter = 0
  previous_display_communication_counter = 0
  timeout_counter_previous = 0

while True:
  
  # process any data received by ESPNow
  espnow_comms.process_data()
  if debug_enable:
    if system_data.display_communication_counter != previous_display_communication_counter:
      previous_display_communication_counter = system_data.display_communication_counter

  # save time value when motion is detected 
  if accelerometer.events.get('motion'):
    last_time_motion_detected = time.monotonic()
    
    if debug_enable:
      motion_counter += 1
      print(f"Motion counter: {motion_counter}")

  # if we should turn off the relay, leave this infinite loop
  if system_data.turn_off_relay:
    if debug_enable:
      print("Turn off relay command")
      
    break

  # if timeout, leave this infinite loop
  timeout_counter = int(time.monotonic() - last_time_motion_detected)
  if timeout_counter > timeout_no_motion_minutes_to_disable_relay:
    break
  
  if debug_enable:
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
# disable relay switch pins
for index in range(len(switch_pins)):
  switch_pins[index].value = False

# wait some time before next movement detection
time.sleep(seconds_to_wait_before_movement_detection)

# pin change alarm, will be active when motion is detected by the ADXL345
pin_alarm_motion_detection = alarm.pin.PinAlarm(int1_pin, value = True)

accelerometer.events.get('motion') # this will clear the interrupt

if debug_enable:
  print("Enter in sleep mode")

alarm.exit_and_deep_sleep_until_alarms(pin_alarm_motion_detection, preserve_dios = switch_pins)
# Does not return. Exits, and restarts after the deep sleep time.

