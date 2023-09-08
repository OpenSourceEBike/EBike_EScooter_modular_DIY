import board
import digitalio
import time
import gc
import espnow_comms

import supervisor
supervisor.runtime.autoreload = False

################################################################
# CONFIGURATIONS

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
turn_lights_blink_counter = 0
turn_lights_blink_state = False

def set_io_pins(io_pins_target):
  # loop over all the pins and set their target values
  for index in range(number_of_pins):
    switch_pins[index].value = True if io_pins_target & (1 << index) else False

while True:
  # check if we received the data
  pins_data = espnow_comms.get_data()
  if pins_data is not None:
    io_pins_target = pins_data
    # reset this counter
    cycles_with_no_received_display_message_counter = 0
  else:
    cycles_with_no_received_display_message_counter += 1
    # after about 2 seconds (200 * 10ms = 2000ms), reset 
    if cycles_with_no_received_display_message_counter % 200 is 0:
      io_pins_target_previous = 0
      set_io_pins(0)
    
  # let's disable here the turn lights pins
  if turn_lights_blink_state is False:
    io_pins_target &= 0b0011

  # will only change the pins if pins target value changed
  if io_pins_target is not io_pins_target_previous:
    io_pins_target_previous = io_pins_target
    set_io_pins(io_pins_target)

  # let's blink turn_lights_blink_state
  # SAE J1690 and associated standards FMVSS 108 and IEC 60809 specify 60 - 120 flashes per minute for turn signals, with 90 per minute as a target.
  # assuming loop of 10ms, 66 * 10ms = 666ms which is 90 times per minute
  turn_lights_blink_counter += 1
  if turn_lights_blink_counter % 25 is 0:
    turn_lights_blink_state = not turn_lights_blink_state

  # do memory clean
  gc.collect()

  # sleep some very little time before do everything again
  time.sleep(0.01)
