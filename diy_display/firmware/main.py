import board
import display
import motor_board_espnow
import system_data as _SystemData
import time
import displayio
from adafruit_display_text import label
import terminalio
import thisbutton as tb
import power_switch_espnow
import rear_lights_espnow
import front_lights_espnow
import wifi
import espnow as _ESPNow

import supervisor
supervisor.runtime.autoreload = False

print("Starting Display")

########################################
# CONFIGURATIONS

# MAC Address value needed for the wireless communication
my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]
mac_address_power_switch_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf1]
mac_address_motor_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]
mac_address_rear_lights_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf4]
mac_address_front_lights_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf5]
########################################

system_data = _SystemData.SystemData()

wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

_espnow = _ESPNow.ESPNow()
motor = motor_board_espnow.MotorBoard(_espnow, mac_address_motor_board, system_data) # System data object to hold the EBike data
power_switch = power_switch_espnow.PowerSwitch(_espnow, mac_address_power_switch_board, system_data)
front_lights = front_lights_espnow.FrontLights(_espnow, mac_address_front_lights_board, system_data)
rear_lights = rear_lights_espnow.RearLights(_espnow, mac_address_rear_lights_board, system_data)

# this will try send data over ESPNow and if there is an error, will restart
system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
# just to check if is possible to send data to motor

displayObject = display.Display(
        board.IO7, # CLK pin
        board.IO9, # MOSI pin
        board.IO5, # chip select pin, not used but for some reason there is an error if chip_select is None
        board.IO12, # command pin
        board.IO11, # reset pin
        1000000) # spi clock frequency
display = displayObject.display

DISPLAY_WIDTH = 64  
DISPLAY_HEIGHT = 128
TEXT = "0"

def filter_motor_power(motor_power):
    
    if motor_power < 0:
        if motor_power > -10:
            motor_power = 0
        elif motor_power > -25:
            pass
        elif motor_power > -50:
            motor_power = round(motor_power / 2) * 2 
        elif motor_power > -100:
            motor_power = round(motor_power / 5) * 5
        else:
            motor_power = round(motor_power / 10) * 10        
    else:
        if motor_power < 10:
            motor_power = 0
        elif motor_power < 25:
            pass
        elif motor_power < 50:
            motor_power = round(motor_power / 2) * 2 
        elif motor_power < 100:
            motor_power = round(motor_power / 5) * 5
        else:
            motor_power = round(motor_power / 10) * 10

    return motor_power

assist_level_area = label.Label(terminalio.FONT, text=TEXT)
assist_level_area.anchor_point = (0.0, 0.0)
assist_level_area.anchored_position = (4, 0)
assist_level_area.scale = 2

battery_voltage_area = label.Label(terminalio.FONT, text=TEXT)
battery_voltage_area.anchor_point = (1.0, 0.0)
battery_voltage_area.anchored_position = (129, 0)
battery_voltage_area.scale = 1

label_x = 61
label_y = 10 + 16
label_1 = label.Label(terminalio.FONT, text=TEXT)
label_1.anchor_point = (1.0, 0.0)
label_1.anchored_position = (label_x, label_y)
label_1.scale = 2

label_x = 129
label_3 = label.Label(terminalio.FONT, text=TEXT)
label_3.anchor_point = (1.0, 0.0)
label_3.anchored_position = (label_x, label_y)
label_3.scale = 2

warning_area = label.Label(terminalio.FONT, text=TEXT)
warning_area.anchor_point = (0.0, 0.0)
warning_area.anchored_position = (2, 48)
warning_area.scale = 1

assist_level = 0
assist_level_state = 0
now = time.monotonic()
buttons_time_previous = now
display_time_previous = now
ebike_rx_tx_data_time_previous = now
lights_send_data_time_previous = now
power_switch_send_data_time_previous = now

battery_voltage_previous_x10 = 9999
battery_current_previous_x100 = 9999
motor_current_previous_x100 = 9999
motor_power_previous = 9999
motor_temperature_x10_previous = 9999
vesc_temperature_x10_previous = 9999
motor_speed_erpm_previous = 9999
brakes_are_active_previous = False
vesc_fault_code_previous = 9999

rear_light_pin_tail_bit = 1
rear_light_pin_stop_bit = 2
rear_light_pin_turn_left_bit = 4
rear_light_pin_turn_right_bit = 8

front_light_pin_head_bit = 1

# keep tail light always on
system_data.rear_lights_board_pins_state = 0

def turn_off_execute():
  global motor, power_switch, front_lights, rear_lights, buttons

  motor.send_data()    

  system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
  power_switch.update()

  front_lights.update()
  rear_lights.update()

def turn_off():
  global system_data, buttons, motor, front_lights, back_lights, power_switch, label_x, label_y, label_1, display

  # new values when turn off the system
  system_data.motor_enable_state = False
  system_data.turn_off_relay = True
  system_data.front_lights_board_pins_state = 0
  system_data.rear_lights_board_pins_state = 0

  label_x = 10
  label_y = 18
  label_1 = label.Label(terminalio.FONT, text="Shutting down")
  label_1.anchor_point = (0.0, 0.0)
  label_1.anchored_position = (label_x, label_y)
  label_1.scale = 1

  g = displayio.Group()
  g.append(label_1)
  display.root_group = g
  
  # wait for button long press release
  while buttons[button_POWER].isHeld:
    buttons[button_POWER].tick()
    turn_off_execute()
    time.sleep(0.05)

  # keep sending the data to the various boards until the system turns off (battery power off),
  # or reset the display if button_POWER is clicked
  while not buttons[button_POWER].buttonActive:
    buttons[button_POWER].tick()
    turn_off_execute()
    time.sleep(0.05)

  # let's reset the display
  import supervisor
  supervisor.reload()
  while True:
    pass

def increase_assist_level():
  global assist_level
  if assist_level < 20:
    assist_level += 1

def decrease_assist_level():
  global assist_level
  if assist_level > 0:
    assist_level -= 1

def button_power_click_start_cb():
  system_data.button_power_state |= 1
  
  # flip bit state
  if system_data.button_power_state & 0x0100:
    system_data.button_power_state &= ~0x0100
  else:
    system_data.button_power_state |= 0x0100
    
def button_power_click_release_cb():
  system_data.button_power_state &= ~1

def button_power_long_click_start_cb():
  # only turn off after initial motor enable
  if system_data.motor_enable_state and system_data.wheel_speed < 2.0:
    turn_off()
  else:
    system_data.button_power_state |= 2
    
  # flip bit state
  if system_data.button_power_state & 0x0200:
    system_data.button_power_state &= ~0x0200
  else:
    system_data.button_power_state |= 0x0200

def button_power_long_click_release_cb():
  system_data.button_power_state &= ~2

def button_left_click_start_cb():
  system_data.rear_lights_board_pins_state |= rear_light_pin_turn_left_bit

def button_left_click_release_cb():
  system_data.rear_lights_board_pins_state &= ~rear_light_pin_turn_left_bit

def button_right_click_start_cb():
  system_data.rear_lights_board_pins_state |= rear_light_pin_turn_right_bit

def button_right_click_release_cb():
  system_data.rear_lights_board_pins_state &= ~rear_light_pin_turn_right_bit

def button_lights_click_start_cb():
  system_data.lights_state = True

def button_lights_click_release_cb():
  system_data.lights_state = False

def button_switch_click_start_cb():
  pass

def button_switch_click_release_cb():
  pass

### Setup buttons ###
button_POWER, button_LEFT, button_RIGHT, button_LIGHTS, button_SWITCH = range(5)
buttons_pins = [
  board.IO39, # button_POWER
  board.IO37, # button_LEFT   
  board.IO35, # button_RIGHT
  board.IO33, # button_LIGHTS 
  board.IO18  # button_SWITCH
]

buttons_callbacks = {
  button_POWER: {
    'click_start': button_power_click_start_cb,
    'click_release': button_power_click_release_cb,
    'long_click_start': button_power_long_click_start_cb,
    'long_click_release': button_power_long_click_release_cb},
  button_LEFT: {
    'click_start': button_left_click_start_cb,
    'click_release': button_left_click_release_cb},
  button_RIGHT: {
    'click_start': button_right_click_start_cb,
    'click_release': button_right_click_release_cb},
  button_LIGHTS: {
    'click_start': button_lights_click_start_cb,
    'click_release': button_lights_click_release_cb},
  button_SWITCH: {
    'click_start': button_switch_click_start_cb,
    'click_release': button_switch_click_release_cb}
}

nr_buttons = len(buttons_pins)
buttons = [0] * nr_buttons
for index in range(nr_buttons):
  buttons[index] = tb.thisButton(buttons_pins[index], True)
  buttons[index].setDebounceThreshold(50)
  buttons[index].setLongPressThreshold(1500)
  # check if each callback is defined, and if so, register it
  if 'click_start' in buttons_callbacks[index]: buttons[index].assignClickStart(buttons_callbacks[index]['click_start'])
  if 'click_release' in buttons_callbacks[index]: buttons[index].assignClickRelease(buttons_callbacks[index]['click_release'])
  if 'long_click_start' in buttons_callbacks[index]: buttons[index].assignLongClickStart(buttons_callbacks[index]['long_click_start'])
  if 'long_click_release' in buttons_callbacks[index]: buttons[index].assignLongClickRelease(buttons_callbacks[index]['long_click_release'])

# show init screen
label_x = 10
label_y = 18
label_init_screen = label.Label(terminalio.FONT, text=TEXT)
label_init_screen.anchor_point = (0.0, 0.0)
label_init_screen.anchored_position = (label_x, label_y)
label_init_screen.scale = 1
label_init_screen.text = "Ready to power on"
screen1_group = displayio.Group()
screen1_group.append(label_init_screen)
display.root_group = screen1_group

# let's wait for a first click on power button
time_previous = time.monotonic()
while True:
  now = time.monotonic()
  if (now - time_previous) > 0.05:
    time_previous = now

    buttons[button_POWER].tick()

    if buttons[button_POWER].buttonActive:

      # wait for user to release the button
      while buttons[button_POWER].buttonActive:
        buttons[button_POWER].tick()

      # motor board will now enable the motor
      system_data.motor_enable_state = True
      break

# show main screen
text_group = displayio.Group()
# text_group.append(assist_level_area)
text_group.append(battery_voltage_area)
text_group.append(label_1)
# text_group.append(label_2)
text_group.append(label_3)
text_group.append(warning_area)
display.root_group = text_group

while True:
    now = time.monotonic()
    if (now - display_time_previous) > 0.1:
        display_time_previous = now

        if battery_voltage_previous_x10 != system_data.battery_voltage_x10:
            battery_voltage_previous_x10 = system_data.battery_voltage_x10
            battery_voltage = system_data.battery_voltage_x10 / 10.0
            battery_voltage_area.text = f"{battery_voltage:2.1f}v"

        # calculate the motor power
        if system_data.motor_speed_erpm < 100:
            system_data.battery_current_x100 = 0

        system_data.motor_power = int((system_data.battery_voltage_x10 * system_data.battery_current_x100) / 1000.0)
        if motor_power_previous != system_data.motor_power:
            motor_power_previous = system_data.motor_power
            motor_power = filter_motor_power(system_data.motor_power)
            label_1.text = f"{motor_power:5}"

        # if motor_current_previous_x100 != system_data.motor_current_x100:
        #     motor_current_previous_x100 = system_data.motor_current_x100

        #     motor_current = int(system_data.motor_current_x100 / 100.0)
        #     label_1.text = f"{motor_current:5}"
        
        # if motor_temperature_sensor_x10_previous != ebike_data.motor_temperature_sensor_x10:
        #     motor_temperature_sensor_x10_previous = ebike_data.motor_temperature_sensor_x10  
        #     label_2.text = str(f"{(ebike_data.motor_temperature_sensor_x10 / 10.0): 2.1f}")

        if motor_speed_erpm_previous != system_data.motor_speed_erpm:
            motor_speed_erpm_previous = system_data.motor_speed_erpm

            if system_data.motor_speed_erpm > 150:
                # Fiido Q1S with installed Luneye motor 2000W
                # calculate the wheel speed
                wheel_radius = 0.165 # measured as 16.5cms
                perimeter = 6.28 * wheel_radius # 2*pi = 6.28
                motor_rpm = system_data.motor_speed_erpm / 15.0 # motor with 15 poles pair
                system_data.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60)

            else:
                system_data.wheel_speed = 0

            label_3.text = f"{system_data.wheel_speed:2.1f}"

    now = time.monotonic()
    if (now - ebike_rx_tx_data_time_previous) > 0.05:
        ebike_rx_tx_data_time_previous = now
        motor.send_data()
        motor.process_data()

        if brakes_are_active_previous != system_data.brakes_are_active:
            brakes_are_active_previous = system_data.brakes_are_active
            if system_data.brakes_are_active:
                warning_area.text = str("brakes")
            else:
                warning_area.text = str("")
        elif vesc_fault_code_previous != system_data.vesc_fault_code:
            vesc_fault_code_previous = system_data.vesc_fault_code
            if system_data.vesc_fault_code:
                warning_area.text = str(f"mot e: {system_data.vesc_fault_code}")
            else:
                warning_area.text = str("")

    now = time.monotonic()
    if (now - lights_send_data_time_previous) > 0.05:
        lights_send_data_time_previous = now

        # if we are braking, enable brake light
        # braking current < 20A
        if system_data.brakes_are_active or system_data.motor_current_x100 < -2000.0:
            system_data.rear_lights_board_pins_state |= rear_light_pin_stop_bit
        else:
            system_data.rear_lights_board_pins_state &= ~rear_light_pin_stop_bit

        # if lights are enable, enable the tail light 
        if system_data.lights_state:
            system_data.front_lights_board_pins_state |= front_light_pin_head_bit
            system_data.rear_lights_board_pins_state |= rear_light_pin_tail_bit
        else:
            system_data.front_lights_board_pins_state &= ~front_light_pin_head_bit
            system_data.rear_lights_board_pins_state &= ~rear_light_pin_tail_bit

        front_lights.update()
        rear_lights.update()

    now = time.monotonic()
    if (now - power_switch_send_data_time_previous) > 0.5:
        power_switch_send_data_time_previous = now

        system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
        power_switch.update()

    now = time.monotonic()
    if (now - buttons_time_previous) > 0.05:
        buttons_time_previous = now

        for index in range(nr_buttons):
            buttons[index].tick()

        # system_data.assist_level = assist_level
        # assist_level_area.text = str(assist_level)


