#########################################################
# Make a beep at boot
import time
import board

import wifi
import display as Display
import ebike_bafang_m500.motor_board_espnow as motor_board_espnow
import vars as Vars
import displayio
from adafruit_display_text import label
import terminalio
import thisbutton as tb
import espnow as _ESPNow
import microcontroller

import supervisor
supervisor.runtime.autoreload = False

print("Starting Display")

########################################
# CONFIGURATIONS

# MAC Address value needed for the wireless communication
my_mac_address =          [0x68, 0xb6, 0xb3, 0x01, 0xa7, 0xb3]
mac_address_motor_board = [0x68, 0xb6, 0xb3, 0x01, 0xa7, 0xb2]
########################################

vars = Vars.Vars()

wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

_espnow = _ESPNow.ESPNow()
motor_board = motor_board_espnow.MotorBoard(_espnow, mac_address_motor_board, vars) # System data object to hold the EBike data

displayObject = Display.Display(
        board.IO3, # CLK / SCK pin
        board.IO4, # MOSI / SDI pin
        board.IO1, # CS pin - chip select pin, not used but for some reason there is an error if chip_select is None
        board.IO2, # DC pin - command pin
        board.IO0, # RST pin - reset pin
        board.IO21, # LED pin - backlight pin
        100000) # spi clock frequency
display = displayObject.display

# show init screen
label_init_screen = label.Label(terminalio.FONT, text='')
label_init_screen.anchor_point = (0.5, 0.5)
label_init_screen.anchored_position = (128/2, 64/2)
label_init_screen.scale = 2
label_init_screen.text = "Ready to\nPOWER ON"
screen1_group = displayio.Group()
screen1_group.append(label_init_screen)
display.root_group = screen1_group

TEXT = ''

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
assist_level_area.anchor_point = (1.0, 0.0)
assist_level_area.anchored_position = (30, 40)
assist_level_area.scale = 2

battery_voltage_area = label.Label(terminalio.FONT, text=TEXT)
battery_voltage_area.anchor_point = (1.0, 0.0)
battery_voltage_area.anchored_position = (37, 4)
battery_voltage_area.scale = 1

motor_power_area = label.Label(terminalio.FONT, text=TEXT)
motor_power_area.anchor_point = (1.0, 0.0)
motor_power_area.anchored_position = (125, 8)
motor_power_area.scale = 4

warning_area = label.Label(terminalio.FONT, text=TEXT)
warning_area.anchor_point = (1.0, 0.0)
warning_area.anchored_position = (121, 52)
warning_area.scale = 1

now = time.monotonic()
buttons_time_previous = now
display_time_previous = now
motor_board_data_time_previous = now

assist_level_previous = 9999
battery_voltage_previous_x10 = 9999
motor_power_previous = 9999
brakes_are_active_previous = False
vesc_fault_code_previous = 9999

refresh_display = False

def turn_off_execute():
  motor_board.send_data()

def turn_off():
  global vars
  global display
  global buttons
  
  # Store assist_level in Non-Volatile Memory
  microcontroller.nvm[0] = vars.assist_level

  # new values when turn off the system
  vars.motor_enable_state = False

  label_1 = label.Label(terminalio.FONT, text="Ready to\nPOWER OFF")
  label_1.anchor_point = (0.5, 0.5)
  label_1.anchored_position = (128/2, 64/2)
  label_1.scale = 2

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

  # let's reset the ESP32-C3 / display
  supervisor.reload()
  while True:
    pass

def increase_assist_level():
  global vars
  global refresh_display
  
  if vars.assist_level < 20:
    vars.assist_level += 1
    
  refresh_display = True

def decrease_assist_level():
  global vars
  global refresh_display
  
  if vars.assist_level > 0:
    vars.assist_level -= 1
    
  refresh_display = True

def button_power_click_start_cb():
  vars.buttons_state |= 1
  
  # flip bit state
  if vars.buttons_state & 0x0100:
    vars.buttons_state &= ~0x0100
  else:
    vars.buttons_state |= 0x0100
    
def button_power_click_release_cb():
  vars.buttons_state &= ~1

def button_power_long_click_start_cb():
  # only turn off after initial motor enable
  if vars.motor_enable_state and vars.wheel_speed_x10 < 20:
    turn_off()
  else:
    vars.buttons_state |= 2
    
  # flip bit state
  if vars.buttons_state & 0x0200:
    vars.buttons_state &= ~0x0200
  else:
    vars.buttons_state |= 0x0200

def button_power_long_click_release_cb():
  vars.buttons_state &= ~2

def button_down_click_start_cb():
  decrease_assist_level()
  
  # flip bit state
  if vars.buttons_state & 0x0400:
    vars.buttons_state &= ~0x0400
  else:
    vars.buttons_state |= 0x0400

def button_down_long_click_start_cb():
  
  # flip bit state
  if vars.buttons_state & 0x0800:
    vars.buttons_state &= ~0x0800
  else:
    vars.buttons_state |= 0x0800

def button_up_click_start_cb():
  increase_assist_level()
  
  # flip bit state
  if vars.buttons_state & 0x1000:
    vars.buttons_state &= ~0x1000
  else:
    vars.buttons_state |= 0x1000
    
def button_up_long_click_start_cb():
  
  # flip bit state
  if vars.buttons_state & 0x2000:
    vars.buttons_state &= ~0x2000
  else:
    vars.buttons_state |= 0x2000

### Setup buttons ###
buttons_pins = [
  board.IO5, # button_POWER
  board.IO6, # button_LEFT   
  board.IO7, # button_RIGHT
]
nr_buttons = len(buttons_pins)
button_POWER, button_DOWN, button_UP = range(nr_buttons)

buttons_callbacks = {
  button_POWER: {
    'click_start': button_power_click_start_cb,
    'click_release': button_power_click_release_cb,
    'long_click_start': button_power_long_click_start_cb,
    'long_click_release': button_power_long_click_release_cb},
  button_DOWN: {
    'click_start': button_down_click_start_cb},
    'long_click_start': button_down_long_click_start_cb,
  button_UP: {
    'click_start': button_up_click_start_cb},
    'long_click_start': button_up_long_click_start_cb,
}

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

      # Exit this loop, continue
      break
    
    # sleep some time to save energy and avoid ESP32-S2 to overheat
    time.sleep(0.025)

# Enable the motor
vars.motor_enable_state = True
    
# reset the buttons_state, as it was changed previously
vars.buttons_state = 0

# show main screen
text_group = displayio.Group()
text_group.append(assist_level_area)
text_group.append(battery_voltage_area)
text_group.append(motor_power_area)
text_group.append(warning_area)
display.root_group = text_group

# Load assist_level from Non-Volatile Memory
vars.assist_level = microcontroller.nvm[0]
if vars.assist_level > 20:
  vars.assist_level = 20
if vars.assist_level < 0:
  vars.assist_level = 0

while True:
    now = time.monotonic()
    if (now - display_time_previous) > 0.5 or \
        refresh_display:
          
        refresh_display = False
        display_time_previous = now

        # Assist level
        if assist_level_previous != vars.assist_level:
            assist_level_previous = vars.assist_level
            assist_level_area.text = f"{vars.assist_level}"
                        
        # Battery voltage
        if battery_voltage_previous_x10 != vars.battery_voltage_x10:
            battery_voltage_previous_x10 = vars.battery_voltage_x10
            battery_voltage = vars.battery_voltage_x10 / 10.0
            battery_voltage_area.text = f"{battery_voltage:2.1f}v"

        # Motor power
        vars.motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x100) / 1000.0)
        if motor_power_previous != vars.motor_power:
            motor_power_previous = vars.motor_power
            motor_power = filter_motor_power(vars.motor_power)
            motor_power_area.text = f"{motor_power:4}"

    # Motor main board
    now = time.monotonic()
    if (now - motor_board_data_time_previous) > 0.05 or \
        refresh_display:
          
        refresh_display = False
        motor_board_data_time_previous = now
        motor_board.send_data()
        motor_board.process_data()

        if brakes_are_active_previous != vars.brakes_are_active:
            brakes_are_active_previous = vars.brakes_are_active
            if vars.brakes_are_active:
                warning_area.text = str("brakes")
            else:
                warning_area.text = str("")
        elif vesc_fault_code_previous != vars.vesc_fault_code:
            vesc_fault_code_previous = vars.vesc_fault_code
            if vars.vesc_fault_code:
                warning_area.text = str(f"mot e: {vars.vesc_fault_code}")
            else:
                warning_area.text = str("")

    # Buttons tick
    now = time.monotonic()
    if (now - buttons_time_previous) > 0.05:
        buttons_time_previous = now

        for index in range(nr_buttons):
            buttons[index].tick()

    # sleep some time to save energy and avoid ESP32-C3 to overheat
    time.sleep(0.01)
