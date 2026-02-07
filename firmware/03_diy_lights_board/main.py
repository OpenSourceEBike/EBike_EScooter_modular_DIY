# main.py - MicroPython version for ESP32-C3 (with hardware watchdog)

import time
import gc
from machine import Pin, WDT

from common.espnow import espnow_init, ESPNowComms
from common.espnow_commands import COMMAND_ID_LIGHTS_1
from common.lights_bits import (
  REAR_TAIL_BIT,
  REAR_BRAKE_BIT,
  REAR_TURN_BITS_MASK,
  REAR_LIGHTS_MASK,
  IO_BITS_MASK,
  NON_TURN_MASK,
)
from common import config_runtime as cfg

################################################################
# CONFIGURATIONS

# MAC address for this lights board (local MAC)
# NOTE: On the ESP32-C3 the Wi-Fi STA has its own MAC. Here we intentionally
# force a fixed MAC. Make sure this makes sense for your ESP-NOW network.
my_mac_address = cfg.mac_address_lights

################################################################
# PRINT BOARD VERSION

print("Starting the DIY Lights board")
print("EBike/EScooter type: " + cfg.type_name)
print()

vehicle_type = cfg.type.get("ebike_escooter") if isinstance(cfg.type, dict) else None
if vehicle_type not in (cfg.TYPE_EBIKE, cfg.TYPE_ESCOOTER):
  raise ValueError("You need to select a valid EBike/EScooter type")

################################################################
################################################################
# IO PINS
#
# NOTE: On the ESP32-C3 the usable pins are typically within 0..21,
# so adjust these according to your hardware setup.
#
# Bit assignments in the unified 8-bit output mask:
#   bit0 -> front low beam   (GPIO0)
#   bit1 -> front high beam  (GPIO1)
#   bit2 -> front turn left  (GPIO2)
#   bit3 -> front turn right (GPIO3)
#   bit4 -> rear tail light  (GPIO21)
#   bit5 -> rear brake light (GPIO20)
#   bit6 -> rear turn left   (GPIO10)
#   bit7 -> rear turn right  (GPIO9)
#
# Incoming ESP-NOW messages are expected as:
#   "<command_id> <mask> <state>"
# where mask/state are full 8-bit values for the unified board.
################################################################

# GPIO mapping per schematic:
#   low, high, front left, front right, tail, brake, rear left, rear right
PIN_NUMBERS = (0, 1, 2, 3, 21, 20, 10, 9)

# Bit positions for the unified 8-bit mask.
DISPLAY_MASK = IO_BITS_MASK & ~REAR_BRAKE_BIT

switch_pins_numbers = list(PIN_NUMBERS)

number_of_pins = len(switch_pins_numbers)
switch_pins = [None] * number_of_pins

# Configure pins as outputs (initially off)
for index, pin_num in enumerate(switch_pins_numbers):
  switch_pins[index] = Pin(pin_num, Pin.OUT, value=0)

################################################################
# ESPNow wireless communications

_sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_lights)

def decode_lights_message(msg):
  parts = [int(s) for s in msg.decode("ascii").split()]
  if len(parts) == 3 and parts[0] == COMMAND_ID_LIGHTS_1:
    return parts
  return None

espnow_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_display),
  decoder=decode_lights_message,
)

# Hardware watchdog: reset the board if not fed within 10 seconds
wdt = WDT(timeout=10000)  # timeout in milliseconds

# Target state for IO pins (bitmask)
io_pins_target = 0
io_pins_target_previous = 0
display_pins_target = 0
display_pins_previous = 0
motor_brake_state = 0
last_display_msg_ms = time.ticks_ms()
last_motor_msg_ms = time.ticks_ms()
last_gc_ms = time.ticks_add(time.ticks_ms(), 1000)

turn_lights_blink_counter = 0
turn_lights_blink_state = False
last_blink_toggle_ms = time.ticks_add(time.ticks_ms(), 375)


def set_io_pins(target: int):
  """
  Set the pins according to the bitmask 'target':
  bit0 -> switch_pins[0]
  bit1 -> switch_pins[1]
  bit2 -> switch_pins[2]
  bit3 -> switch_pins[3]
  bit4 -> switch_pins[4]
  bit5 -> switch_pins[5]
  bit6 -> switch_pins[6]
  bit7 -> switch_pins[7]
  """
  for index in range(number_of_pins):
    bit = (1 << index)
    switch_pins[index].value(1 if (target & bit) else 0)


################################################################
# MAIN LOOP
################################################################

LOOP_INTERVAL_MS = 25  # target loop time in milliseconds

while True:
  loop_start_ms = time.ticks_ms()

  # Feed the hardware watchdog at the beginning of each loop
  wdt.feed()

  # Check if new ESP-NOW data was received
  msg = espnow_comms.get_data()
  if msg is not None:
    command_id, mask, state = msg
    if command_id == COMMAND_ID_LIGHTS_1:
      if mask & REAR_BRAKE_BIT:
        # Motor main board controls brake light only
        motor_brake_state = REAR_BRAKE_BIT if (state & REAR_BRAKE_BIT) else 0
        last_motor_msg_ms = time.ticks_ms()
      else:
        # Display does not control brake light
        mask &= DISPLAY_MASK
        masked_state = state & mask & DISPLAY_MASK
        display_pins_target = (display_pins_target & (~mask & DISPLAY_MASK)) | masked_state
        display_pins_previous = display_pins_target
        last_display_msg_ms = time.ticks_ms()
  else:
    # Reuse previous value if nothing new was received
    display_pins_target = display_pins_previous

  # After ~2 seconds with no display messages, reset display-driven pins
  if time.ticks_diff(time.ticks_ms(), last_display_msg_ms) >= 2000:
    display_pins_target = 0
    display_pins_previous = 0

  # After ~2 seconds with no motor messages, clear brake light
  if time.ticks_diff(time.ticks_ms(), last_motor_msg_ms) >= 2000:
    motor_brake_state = 0

  io_pins_target = (display_pins_target & DISPLAY_MASK) | motor_brake_state

  # Rear behavior (tail/brake + turns)
  if io_pins_target & REAR_BRAKE_BIT:
    # Clear tail when brake is on
    io_pins_target &= ~REAR_TAIL_BIT

  # Disable tail and brake lights when rear turn lights are active
  if io_pins_target & REAR_TURN_BITS_MASK:
    io_pins_target &= ~REAR_LIGHTS_MASK

  # Disable turn signal outputs if blink state is OFF
  if not turn_lights_blink_state:
    io_pins_target &= NON_TURN_MASK

  # Update the output pins only if target value changed
  if io_pins_target != io_pins_target_previous:
    io_pins_target_previous = io_pins_target
    set_io_pins(io_pins_target)

  # Blink turn_lights_blink_state
  #
  # 60–120 flashes per minute are acceptable; we target ~80 flashes/min.
  # 375 ms per half-period -> 750 ms per full on/off cycle.
  if time.ticks_diff(time.ticks_ms(), last_blink_toggle_ms) >= 0:
    last_blink_toggle_ms = time.ticks_add(last_blink_toggle_ms, 375)
    turn_lights_blink_state = not turn_lights_blink_state

  # Periodic garbage collection
  if time.ticks_diff(time.ticks_ms(), last_gc_ms) >= 0:
    last_gc_ms = time.ticks_add(last_gc_ms, 1000)
    gc.collect()

  # Try to maintain a 25 ms loop time
  elapsed_ms = time.ticks_diff(time.ticks_ms(), loop_start_ms)
  next_sleep_ms = LOOP_INTERVAL_MS - elapsed_ms

  # Avoid extremely small or negative delays
  if next_sleep_ms < 1:
    next_sleep_ms = 1

  time.sleep_ms(next_sleep_ms)
