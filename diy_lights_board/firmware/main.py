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
switch_pins = [0] * len(switch_pins_numbers)

# configure the pins as outputs and disable
for index, switch_pin_number in enumerate(switch_pins_numbers):
  switch_pins[index] = digitalio.DigitalInOut(switch_pin_number)
  switch_pins[index].direction = digitalio.Direction.OUTPUT
  switch_pins[index].value = False

espnow_comms = espnow_comms.ESPNowComms(my_mac_address, message_id)

while True:
  # check if we received the data
  io_pins_target = espnow_comms.get_data()
  if io_pins_target is not None:

    # loop over all the pins and set their target values
    for index, switch_pin_number in enumerate(switch_pins_numbers):
      switch_pins[index].value = True if io_pins_target & (1 << index) else False

  # do memory clean
  gc.collect()

  # sleep some very little time before do everything again
  time.sleep(0.02)
