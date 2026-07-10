# main.py - MicroPython version for ESP32-C3

import time
import gc
from machine import Pin

from common.espnow import espnow_init, ESPNowComms
from common.espnow_protocol import (
  BOARD_DISPLAY,
  BOARD_LIGHTS,
  BOARD_MOTOR,
  MSG_COMMAND,
  parse_frame,
)
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
LIGHTS_DEBUG = False


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
#   MSG_COMMAND, src, dst, mask, state
# where src may be display or motor, dst is this lights board, and
# mask/state are full 8-bit values for the unified board.
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
  parts = parse_frame(msg)
  if parts is None:
    return None
  if len(parts) == 5 and parts[0] == MSG_COMMAND and parts[2] == BOARD_LIGHTS and parts[1] in (BOARD_DISPLAY, BOARD_MOTOR):
    return parts
  return None

espnow_comms = ESPNowComms(
  esp,
  bytes(cfg.mac_address_motor_board),
  decoder=decode_lights_message,
)

DISPLAY_TIMEOUT_MS = 20000
MOTOR_TIMEOUT_MS = 2000

# Target state for IO pins (bitmask)
io_pins_target = 0
io_pins_target_previous = 0
display_pins_target = 0
display_pins_previous = 0
motor_brake_state = 0
display_timeout_ms = time.ticks_add(time.ticks_ms(), DISPLAY_TIMEOUT_MS)
motor_timeout_ms = time.ticks_add(time.ticks_ms(), MOTOR_TIMEOUT_MS)
last_gc_ms = time.ticks_add(time.ticks_ms(), 1000)
lights_debug_next_ms = time.ticks_add(time.ticks_ms(), 1000)

turn_lights_blink_counter = 0
turn_lights_blink_state = False
last_blink_toggle_ms = time.ticks_add(time.ticks_ms(), 375)

tail_brake_blink_state = True
tail_brake_next_toggle_ms = time.ticks_add(time.ticks_ms(), cfg.brake_tail_on_ms)

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
  now = loop_start_ms

  # Check if new ESP-NOW data was received
  msg = espnow_comms.get_data()
  if msg is not None:
    command_id, src_id, dst_id, mask, state = msg
    if command_id == MSG_COMMAND:
      if mask & REAR_BRAKE_BIT:
        # Motor board controls brake light only
        motor_brake_state = REAR_BRAKE_BIT if (state & REAR_BRAKE_BIT) else 0
        motor_timeout_ms = time.ticks_add(now, MOTOR_TIMEOUT_MS)
      else:
        # Motor board does not control brake light
        mask &= DISPLAY_MASK
        masked_state = state & mask & DISPLAY_MASK
        display_pins_target = (display_pins_target & (~mask & DISPLAY_MASK)) | masked_state
        display_pins_previous = display_pins_target
        display_timeout_ms = time.ticks_add(now, DISPLAY_TIMEOUT_MS)
  else:
    # Reuse previous value if nothing new was received
    display_pins_target = display_pins_previous

  # After DISPLAY_TIMEOUT_MS with no display messages, reset display-driven pins
  if time.ticks_diff(now, display_timeout_ms) >= 0:
    display_pins_target = 0
    display_pins_previous = 0

  # After ~2 seconds with no motor messages, clear brake light
  if time.ticks_diff(now, motor_timeout_ms) >= 0:
    motor_brake_state = 0

  io_pins_target = (display_pins_target & DISPLAY_MASK) | motor_brake_state

  # Rear behavior (tail/brake + turns)
  if io_pins_target & REAR_BRAKE_BIT:
    if cfg.brake_tail_blink_enable:
      # Blink tail when brake is active (900ms ON / 100ms OFF by default)
      if time.ticks_diff(now, tail_brake_next_toggle_ms) >= 0:
        if tail_brake_blink_state:
          tail_brake_blink_state = False
          tail_brake_next_toggle_ms = time.ticks_add(
            tail_brake_next_toggle_ms, cfg.brake_tail_off_ms
          )
        else:
          tail_brake_blink_state = True
          tail_brake_next_toggle_ms = time.ticks_add(
            tail_brake_next_toggle_ms, cfg.brake_tail_on_ms
          )
      if tail_brake_blink_state:
        io_pins_target |= REAR_TAIL_BIT
      else:
        io_pins_target &= ~REAR_TAIL_BIT
  else:
    # Reset blink timing so the next brake starts with ON
    if cfg.brake_tail_blink_enable:
      tail_brake_blink_state = True
      tail_brake_next_toggle_ms = time.ticks_add(
        now, cfg.brake_tail_on_ms
      )

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

  if LIGHTS_DEBUG and time.ticks_diff(now, lights_debug_next_ms) >= 0:
    lights_debug_next_ms = time.ticks_add(lights_debug_next_ms, 1000)
    print(
      "lights bits: display=0x{:02X}, motor=0x{:02X}, out=0x{:02X}".format(
        int(display_pins_target),
        int(motor_brake_state),
        int(io_pins_target),
      )
    )

  # Blink turn_lights_blink_state
  #
  # 60–120 flashes per minute are acceptable; we target ~80 flashes/min.
  # 375 ms per half-period -> 750 ms per full on/off cycle.
  if time.ticks_diff(now, last_blink_toggle_ms) >= 0:
    last_blink_toggle_ms = time.ticks_add(last_blink_toggle_ms, 375)
    turn_lights_blink_state = not turn_lights_blink_state

  # Periodic garbage collection
  if time.ticks_diff(now, last_gc_ms) >= 0:
    last_gc_ms = time.ticks_add(last_gc_ms, 1000)
    gc.collect()

  # Try to maintain a 25 ms loop time
  next_loop_ms = time.ticks_add(loop_start_ms, LOOP_INTERVAL_MS)
  next_sleep_ms = time.ticks_diff(next_loop_ms, time.ticks_ms())

  # Avoid extremely small or negative delays
  if next_sleep_ms < 1:
    next_sleep_ms = 1

  time.sleep_ms(next_sleep_ms)
