# main.py - MicroPython version for ESP32-C3 (with hardware watchdog)

import time
import gc
from machine import Pin, WDT

from constants import FRONT_VERSION, REAR_VERSION
import common.config_runtime as cfg
from espnow_comms import ESPNowComms

################################################################
# CONFIGURATIONS

# Select which board this firmware is running on
lights_board = FRONT_VERSION  # or REAR_VERSION

# MAC address for this lights board (local MAC)
# NOTE: On the ESP32-C3 the Wi-Fi STA has its own MAC. Here we intentionally
# force a fixed MAC. Make sure this makes sense for your ESP-NOW network.
if lights_board == FRONT_VERSION:
    # Front lights board ESP-NOW MAC address
    my_mac_address = cfg.mac_address_front_lights
elif lights_board == REAR_VERSION:
    # Rear lights board ESP-NOW MAC address
    my_mac_address = cfg.mac_address_rear_lights
else:
    raise ValueError("Invalid lights_board selection")

################################################################
# PRINT BOARD VERSION

if lights_board == FRONT_VERSION:
    print("Starting the DIY Lights board - FRONT version")
else:
    print("Starting the DIY Lights board - REAR version")

################################################################
# IO PINS
#
# NOTE: On the ESP32-C3 the usable pins are typically within 0..21,
# so adjust these according to your hardware setup.
################################################################

switch_pins_numbers = [0, 1, 2, 3]
number_of_pins = len(switch_pins_numbers)
switch_pins = [None] * number_of_pins

# Configure pins as outputs (initially off)
for index, pin_num in enumerate(switch_pins_numbers):
    switch_pins[index] = Pin(pin_num, Pin.OUT, value=0)

# ESP-NOW communication interface
espnow_comms = ESPNowComms(my_mac_address, lights_board)

# Hardware watchdog: reset the board if not fed within 5 seconds
wdt = WDT(timeout=5000)  # timeout in milliseconds

# Target state for IO pins (bitmask)
io_pins_target = 0
io_pins_target_previous = 0
cycles_with_no_received_display_message_counter = 0

# Variables only used when running REAR_VERSION
turn_lights_blink_counter = 0
turn_lights_blink_state = False


def set_io_pins(target: int):
    """
    Set the pins according to the bitmask 'target':
    bit0 -> switch_pins[0]
    bit1 -> switch_pins[1]
    bit2 -> switch_pins[2]
    bit3 -> switch_pins[3]
    """
    for index in range(number_of_pins):
        bit = (1 << index)
        switch_pins[index].value(1 if (target & bit) else 0)


pins_data_previous = 0

################################################################
# MAIN LOOP
################################################################

LOOP_INTERVAL_MS = 25  # target loop time in milliseconds

while True:
    loop_start_ms = time.ticks_ms()

    # Feed the hardware watchdog at the beginning of each loop
    wdt.feed()

    # Check if new ESP-NOW data was received
    pins_data = espnow_comms.get_data()
    if pins_data is not None:
        pins_data_previous = pins_data
        io_pins_target = pins_data
        # Reset timeout counter
        cycles_with_no_received_display_message_counter = 0
    else:
        # Reuse previous value if nothing new was received
        io_pins_target = pins_data_previous
        cycles_with_no_received_display_message_counter += 1

        # After ~2 seconds (80 * 25ms = 2000ms), reset pins
        if (cycles_with_no_received_display_message_counter % 80) == 0:
            io_pins_target_previous = 0
            # Disable all pins
            set_io_pins(0)

    # Force tail-light off if brake-light is active
    # Assuming:
    #   bit0 -> tail
    #   bit1 -> brake
    if io_pins_target & 0b0010:
        # Clear tail (bit0) when brake (bit1) is on
        io_pins_target &= 0b1110

    if lights_board == REAR_VERSION:
        # Disable tail and brake lights when turn lights are active
        # Assuming:
        #   bit2 -> left turn
        #   bit3 -> right turn
        if io_pins_target & 0b1100:
            io_pins_target &= 0b1100

        # Disable turn signal outputs if blink state is OFF
        if not turn_lights_blink_state:
            io_pins_target &= 0b0011

    # Update the output pins only if target value changed
    if io_pins_target != io_pins_target_previous:
        io_pins_target_previous = io_pins_target
        set_io_pins(io_pins_target)

    if lights_board == REAR_VERSION:
        # Blink turn_lights_blink_state
        #
        # 60–120 flashes per minute are acceptable; we target ~80 flashes/min.
        # With a 25 ms loop:
        #   25 ms * 15 ≈ 375 ms per half-period
        #   -> 750 ms per full on/off cycle ≈ 80 cycles/min
        turn_lights_blink_counter += 1
        if (turn_lights_blink_counter % 15) == 0:
            turn_lights_blink_state = not turn_lights_blink_state

    # Force garbage collection
    gc.collect()

    # Try to maintain a 25 ms loop time
    elapsed_ms = time.ticks_diff(time.ticks_ms(), loop_start_ms)
    next_sleep_ms = LOOP_INTERVAL_MS - elapsed_ms

    # Avoid extremely small or negative delays
    if next_sleep_ms < 1:
        next_sleep_ms = 1

    time.sleep_ms(next_sleep_ms)
