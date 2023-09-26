import supervisor
supervisor.runtime.autoreload = False

import board
import digitalio
import time
import gc
import espnow_comms

FRONT_VERSION, REAR_VERSION = range(2)

################################################################
# CONFIGURATIONS

lights_board = REAR_VERSION
disable_tail_brake_while_blink_on = True

if lights_board is FRONT_VERSION:
  # front lights board ESPNow MAC Address
  my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf5]

  # front lights board ESPNow messages ID = 8
  message_id = 16
elif lights_board is REAR_VERSION:
  # rear lights board ESPNow MAC Address
  my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf4]

  # rear lights board ESPNow messages ID = 8
  message_id = 8

################################################################

# enable the IO pins
switch_pins_numbers = [board.IO33, board.IO35, board.IO37, board.IO39]
number_of_pins = len(switch_pins_numbers)
switch_pins = [0] * number_of_pins

# configure the pins as outputs and disable
for index in range (number_of_pins):
  switch_pins[index] = digitalio.DigitalInOut(switch_pins_numbers[index])
  switch_pins[index].direction = digitalio.Direction.OUTPUT
  switch_pins[index].value = False

espnow_comms = espnow_comms.ESPNowComms(my_mac_address, message_id)

io_pins_target = 0
io_pins_target_previous = 0
cycles_with_no_received_display_message_counter = 0

# variables only used on REAR_VERSION
if lights_board is REAR_VERSION:
  turn_lights_blink_counter = 0
  turn_lights_blink_state = False

def set_io_pins(io_pins_target):
  # loop over all the pins and set their target values
  for index in range(number_of_pins):
    switch_pins[index].value = True if io_pins_target & (1 << index) else False

pins_data_previous = 0
while True:
  loop_code_time_begin = time.monotonic()

  # check if we received the data
  pins_data = espnow_comms.get_data()
  if pins_data is not None:
    pins_data_previous = pins_data
    io_pins_target = pins_data
    # reset this counter
    cycles_with_no_received_display_message_counter = 0
  else:
    # use the previous value if there is no new received value
    io_pins_target = pins_data_previous
    cycles_with_no_received_display_message_counter += 1
    # after about 2 seconds (80 * 25ms = 2000ms), reset 
    if cycles_with_no_received_display_message_counter % 80 is 0:
      io_pins_target_previous = 0
      # disable all pins
      set_io_pins(0)

  # force disable tail light if brake light is active
  if io_pins_target & 0b0010:
    io_pins_target &= 0b1110

  # if lights_board is REAR_VERSION:
  #   # disable turn lights if blink state is False
  #   if turn_lights_blink_state is False:
  #     io_pins_target &= 0b0011
  #   else:
  #     if disable_tail_brake_while_blink_on is True:
  #       if io_pins_target & 0b1100:
  #         # disable tail or brake lights while 
  #         io_pins_target &= 0b1100

  if lights_board is REAR_VERSION:
    # disable tail and brake lights if turn lights are active
    if io_pins_target & 0b1100:
      io_pins_target &= 0b1100

    # disable turn lights if blink state is False
    if turn_lights_blink_state is False:
      io_pins_target &= 0b0011

  # will only change the pins if pins target value changed
  if io_pins_target is not io_pins_target_previous:
    io_pins_target_previous = io_pins_target
    set_io_pins(io_pins_target)

  if lights_board is REAR_VERSION:
    # let's blink turn_lights_blink_state
    # SAE J1690 and associated standards FMVSS 108 and IEC 60809 specify 60 - 120 flashes per minute for turn signals, with 90 per minute as a target.
    # assuming loop of 25ms, 25 * 25ms = 625ms which is about 90 times per minute
    turn_lights_blink_counter += 1
    if turn_lights_blink_counter % 15 is 0:
      turn_lights_blink_state = not turn_lights_blink_state

  # do memory clean
  gc.collect()

  # try to get 25ms loop time
  loop_code_total_time = time.monotonic() - loop_code_time_begin
  next_sleep_time = 0.025 - loop_code_total_time
  # avoid to small or even negative values
  if next_sleep_time < 0.001:
    next_sleep_time = 0.001

  time.sleep(next_sleep_time)
