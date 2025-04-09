class ESP32Board:
  ESP32_S2 = 0
  ESP32_C3 = 1

# esp32_board = ESP32Board.ESP32_S2
esp32_board = ESP32Board.ESP32_C3

#########################################################
# Make a beep at boot
import time
import board
import escooter_fiido_q1_s.buzzer as Buzzer

if esp32_board == ESP32Board.ESP32_S2:
  buzzer_pins = [
    board.IO16,
  ]
elif esp32_board == ESP32Board.ESP32_C3:
    buzzer_pins = [
    board.IO20,
  ]
  
buzzer = Buzzer.Buzzer(buzzer_pins)
buzzer.duty_cycle = 0.03
time.sleep(0.5)  
buzzer.duty_cycle = 0.0
#########################################################

import wifi
import display as Display
import escooter_fiido_q1_s.motor_board_espnow as motor_board_espnow
import vars as Vars
import displayio
from adafruit_display_text import label
import terminalio
import thisbutton as tb
import escooter_fiido_q1_s.power_switch_espnow as power_switch_espnow
import escooter_fiido_q1_s.rear_lights_espnow as rear_lights_espnow
import escooter_fiido_q1_s.front_lights_espnow as front_lights_espnow
import espnow as _ESPNow
import escooter_fiido_q1_s.rtc_date_time as rtc_date_time
import vectorio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.line import Line

import supervisor
supervisor.runtime.autoreload = False

print("Starting Display")


# import digitalio
# lights_button = digitalio.DigitalInOut(board.IO33)
# lights_button.direction = digitalio.Direction.INPUT

# while True:
#   print(1 if lights_button.value else 0)
  
#   time.sleep(1)


########################################
# CONFIGURATIONS

# MAC Address value needed for the wireless communication
my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]
mac_address_power_switch_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf1]
mac_address_motor_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]
mac_address_rear_lights_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf4]
mac_address_front_lights_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf5]
########################################

vars = Vars.Vars()

wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

rtc = rtc_date_time.RTCDateTime(board.IO9, board.IO8)

_espnow = _ESPNow.ESPNow()
motor = motor_board_espnow.MotorBoard(_espnow, mac_address_motor_board, vars) # System data object to hold the EBike data
power_switch = power_switch_espnow.PowerSwitch(_espnow, mac_address_power_switch_board, vars)
front_lights = front_lights_espnow.FrontLights(_espnow, mac_address_front_lights_board, vars)
rear_lights = rear_lights_espnow.RearLights(_espnow, mac_address_rear_lights_board, vars)

# this will try send data over ESPNow and if there is an error, will restart
vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024
# just to check if is possible to send data to motor

if esp32_board == ESP32Board.ESP32_S2:
  displayObject = Display.Display(
    board.IO11, # CLK pin
    board.IO12, # MOSI pin
    board.IO7, # chip select pin, not used but for some reason there is an error if chip_select is None
    board.IO9, # command pin
    board.IO5, # reset pin
    board.IO3, # backlight pin
    1000000) # spi clock frequency
    
elif esp32_board == ESP32Board.ESP32_C3:
  displayObject = Display.Display(
    board.IO3, # CLK / SCK pin
    board.IO4, # MOSI / SDI pin
    board.IO1, # CS pin - chip select pin, not used but for some reason there is an error if chip_select is None
    board.IO2, # DC pin - command pin
    board.IO0, # RST pin - reset pin
    board.IO21, # LED pin - backlight pin
    1000000) # spi clock frequency

display = displayObject.display

FreeSans_20 = bitmap_font.load_font("fonts/FreeSans-20.bdf")
FreeSansBold_20 = bitmap_font.load_font("fonts/FreeSansBold-20.bdf")
FreeSansBold_50 = bitmap_font.load_font("fonts/FreeSansBold-50.bdf")

# show init screen
label_init_screen = label.Label(FreeSansBold_20, text='')
label_init_screen.anchor_point = (0.5, 0.5)
label_init_screen.anchored_position = (128/2, 63/2)
label_init_screen.scale = 1
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

# battery voltage
label_battery_voltage = label.Label(terminalio.FONT, text='')
label_battery_voltage.anchor_point = (1.0, 1.0)
label_battery_voltage.anchored_position = (30, 64)

# wheel speed
label_speed = label.Label(FreeSansBold_50, text='')
label_speed.anchor_point = (1.0, 0.0)
label_speed.anchored_position = (128, 0)

# time
label_time = label.Label(FreeSans_20, text='')
label_time.anchor_point = (1.0, 1.0)
label_time.anchored_position = (128, 63)

# warning area
label_warning_area = label.Label(terminalio.FONT, text=TEXT)
label_warning_area.anchor_point = (0.0, 1.0)
label_warning_area.anchored_position = (0, 64)

palette_white = displayio.Palette(1)
palette_white[0] = 0x000000  # background

palette_black = displayio.Palette(1)
palette_black[0] = 0xFFFFFF  # fill bar

# Background bar (constant size)
motor_power_width = 57
motor_power_height = 32
motor_power_x = 2
motor_power_y = 2

motor_power_bg = vectorio.Rectangle(
  pixel_shader=palette_white,
  width=motor_power_width,
  height=motor_power_height,
  x=motor_power_x,
  y=motor_power_y
)

# Foreground bar (fill) — will be replaced on update
motor_power_fill = vectorio.Rectangle(
  pixel_shader=palette_black,
  width=1,
  height=motor_power_height,
  x=motor_power_x,
  y=motor_power_y
)

def draw_motor_power_scale():
  global main_display_group
  
  s_x = 0 # start_x
  s_y = 0 # start_y
  h = 35 # height
  w = 60 # width
  w_2 = int(w/2) # width
  bar_width = 4

  l1 = Line(s_x, s_y+h, s_x, s_y,                          color=palette_black[0])
  l2 = Line(s_x, s_y+h, w_2, s_y+h,                        color=palette_black[0])
  l3 = Line(w_2, s_y+h, w_2, s_y+h-bar_width,              color=palette_black[0])
  l4 = Line(w_2, s_y+h, w, s_y+h,                          color=palette_black[0])
  l5 = Line(w, s_y+h, w, s_y+h-bar_width,                  color=palette_black[0])
  
  l6 = Line(s_x, s_y, w_2, s_y,                            color=palette_black[0])
  l7 = Line(w_2, s_y, w_2, s_y+bar_width,                  color=palette_black[0])
  l8 = Line(w_2, s_y, w, s_y,                              color=palette_black[0])
  l9 = Line(w, s_y, w, s_y+bar_width,                      color=palette_black[0])
  
  main_display_group.append(l1)
  main_display_group.append(l2)
  main_display_group.append(l3)
  main_display_group.append(l4)
  main_display_group.append(l5)
  main_display_group.append(l6)
  main_display_group.append(l7)
  main_display_group.append(l8)
  main_display_group.append(l9)

assist_level = 0
assist_level_state = 0
now = time.monotonic()
buttons_time_previous = now
display_time_previous = now
ebike_rx_tx_data_time_previous = now
lights_send_data_time_previous = now
power_switch_send_data_time_previous = now
turn_lights_buzzer_time_previous = now
update_date_time_previous = now
update_date_time_once = False
date_time_updated = None
date_time_previous = now

battery_voltage_previous_x10 = 9999
battery_current_previous_x100 = 9999
motor_current_previous_x100 = 9999
motor_power_previous = 9999
motor_temperature_x10_previous = 9999
vesc_temperature_x10_previous = 9999
motor_speed_erpm_previous = 9999
wheel_speed_x10_previous = 9999
brakes_are_active_previous = False
vesc_fault_code_previous = 9999

rear_light_pin_tail_bit = 1
rear_light_pin_stop_bit = 2
rear_light_pin_turn_left_bit = 4
rear_light_pin_turn_right_bit = 8

front_light_pin_head_bit = 1

turn_lights_buzzer_state = False

# keep tail light always on
vars.rear_lights_board_pins_state = 0

def turn_off_execute():

  motor.send_data()    

  vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024
  power_switch.send_data()

  front_lights.send_data()
  rear_lights.send_data()

def turn_off():

  # new values when turn off the system
  vars.motor_enable_state = False
  vars.turn_off_relay = True
  vars.front_lights_board_pins_state = 0
  vars.rear_lights_board_pins_state = 0

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
    time.sleep(0.15)

  # keep sending the data to the various boards until the system turns off (battery power off),
  # or reset the display if button_POWER is clicked
  while not buttons[button_POWER].buttonActive:
    buttons[button_POWER].tick()
    turn_off_execute()
    time.sleep(0.15)

  # let's reset the display
  supervisor.reload()
  while True:
    pass

def increase_assist_level():
  if assist_level < 20:
    assist_level += 1

def decrease_assist_level():
  if assist_level > 0:
    assist_level -= 1

def button_power_click_start_cb():
  vars.buttons_state |= 1
  
  # flip bit state
  if vars.buttons_state & 0x0100:
    vars.buttons_state &= ~0x0100
  else:
    vars.buttons_state |= 0x0100
    
#  if system_data.motor_enable_state:
#    system_data.lights_state = not system_data.lights_state
    
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

def button_left_click_start_cb():
  vars.rear_lights_board_pins_state |= rear_light_pin_turn_left_bit

def button_left_click_release_cb():
  vars.rear_lights_board_pins_state &= ~rear_light_pin_turn_left_bit

def button_right_click_start_cb():
  vars.rear_lights_board_pins_state |= rear_light_pin_turn_right_bit

def button_right_click_release_cb():
  vars.rear_lights_board_pins_state &= ~rear_light_pin_turn_right_bit

def button_lights_click_start_cb():
  vars.lights_state = True

def button_lights_click_release_cb():
  vars.lights_state = False

### Setup buttons ###
if esp32_board == ESP32Board.ESP32_S2:
  buttons_pins = [
    board.IO17, # button_POWER
    # board.IO6, # button_LEFT   
    # board.IO7, # button_RIGHT
    # board.IO10, # button_LIGHTS
    board.IO21, # button_LIGHTS 
  ]
    
elif esp32_board == ESP32Board.ESP32_C3:
  buttons_pins = [
    board.IO5, # button_POWER
    # board.IO6, # button_LEFT   
    # board.IO7, # button_RIGHT
    # board.IO10, # button_LIGHTS
    board.IO6, # button_LIGHTS 
  ]

nr_buttons = len(buttons_pins)
#button_POWER, button_LEFT, button_RIGHT, button_LIGHTS = range(nr_buttons)
button_POWER, button_LIGHTS = range(nr_buttons)

buttons_callbacks = {
  button_POWER: {
    'click_start': button_power_click_start_cb,
    'click_release': button_power_click_release_cb,
    'long_click_start': button_power_long_click_start_cb,
    'long_click_release': button_power_long_click_release_cb},
  # button_LEFT: {
  #   'click_start': button_left_click_start_cb,
  #   'click_release': button_left_click_release_cb},
  # button_RIGHT: {
  #   'click_start': button_right_click_start_cb,
  #   'click_release': button_right_click_release_cb},
  button_LIGHTS: {
    'click_start': button_lights_click_start_cb,
    'click_release': button_lights_click_release_cb},
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

      # motor board will now enable the motor
      vars.motor_enable_state = True
      break
    
    # sleep some time to save energy and avoid ESP32-S2 to overheat
    time.sleep(0.025)

vars.motor_enable_state = True
    
# reset the buttons_state, as it was changed previously
vars.buttons_state = 0

# show main screen
main_display_group = displayio.Group()
main_display_group.append(label_battery_voltage)
main_display_group.append(label_speed)
main_display_group.append(label_time)
main_display_group.append(label_warning_area)
main_display_group.append(motor_power_bg)
main_display_group.append(motor_power_fill)
draw_motor_power_scale()
display.root_group = main_display_group

def draw_motor_power(motor_power):
  global motor_power_fill
  global main_display_group

  motor_power = max(0, min(motor_power, 100))
  width_motor_power = max(1, int(motor_power_width * (motor_power / 100)))

  # Try remove old bar
  try:
    main_display_group.remove(motor_power_fill)
  except ValueError:
    pass
  
  # Create new bar with updated width
  if motor_power > 0:
    motor_power_fill = vectorio.Rectangle(
      pixel_shader=palette_black,
      width=width_motor_power,
      height=motor_power_height,
      x=motor_power_x,
      y=motor_power_y
    )

    # Add updated bar back in
    main_display_group.append(motor_power_fill)


while True:
    now = time.monotonic()
    if (now - display_time_previous) > 0.1:
        display_time_previous = now

        # battery
        if battery_voltage_previous_x10 != vars.battery_voltage_x10:
            battery_voltage_previous_x10 = vars.battery_voltage_x10
            battery_voltage = vars.battery_voltage_x10 / 10.0
            label_battery_voltage.text = f"{battery_voltage:2.1f}v"

        # motor power
        vars.motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x100) / 1000.0)
        if motor_power_previous != vars.motor_power:
            motor_power_previous = vars.motor_power
            motor_power = filter_motor_power(vars.motor_power)
            motor_power_percent = int((motor_power * 100) / 2000.0)
            draw_motor_power(motor_power_percent)
            
        # wheel speed
        if wheel_speed_x10_previous != vars.wheel_speed_x10:
            wheel_speed_x10_previous = vars.wheel_speed_x10  
            label_speed.text = f"{int(vars.wheel_speed_x10 / 10.0)}"

    now = time.monotonic()
    if (now - ebike_rx_tx_data_time_previous) > 0.15:
        ebike_rx_tx_data_time_previous = now
        motor.send_data()
        motor.process_data()
        
        if brakes_are_active_previous != vars.brakes_are_active:
            brakes_are_active_previous = vars.brakes_are_active
            if vars.brakes_are_active:
              
                # try:
                #   main_display_group.remove(label_battery_voltage)
                # except ValueError:
                #   pass
                
                label_warning_area.text = str("brakes")
            else:
                label_warning_area.text = str("")
                # main_display_group.append(label_battery_voltage)
                
        elif vesc_fault_code_previous != vars.vesc_fault_code:
            vesc_fault_code_previous = vars.vesc_fault_code
            if vars.vesc_fault_code:
                label_warning_area.text = str(f"mot e: {vars.vesc_fault_code}")
            else:
                label_warning_area.text = str("")

    now = time.monotonic()
    if (now - lights_send_data_time_previous) > 0.05:
        lights_send_data_time_previous = now

        # if we are braking, enable brake light
        # braking current < 15A
        if vars.brakes_are_active or vars.motor_current_x100 < -1500:
            vars.rear_lights_board_pins_state |= rear_light_pin_stop_bit
        else:
            vars.rear_lights_board_pins_state &= ~rear_light_pin_stop_bit

        # if lights are enable, enable the tail light 
        if vars.lights_state:
            vars.front_lights_board_pins_state |= front_light_pin_head_bit
            vars.rear_lights_board_pins_state |= rear_light_pin_tail_bit
        else:
            vars.front_lights_board_pins_state &= ~front_light_pin_head_bit
            vars.rear_lights_board_pins_state &= ~rear_light_pin_tail_bit

        front_lights.send_data()
        rear_lights.send_data()


    now = time.monotonic()  
    if vars.rear_lights_board_pins_state & rear_light_pin_turn_left_bit or \
        vars.rear_lights_board_pins_state & rear_light_pin_turn_right_bit:
          
          if (now - turn_lights_buzzer_time_previous) > 0.5:
              turn_lights_buzzer_time_previous = now
          
              if turn_lights_buzzer_state:
                  buzzer.duty_cycle = 0.03
              else:
                  buzzer.duty_cycle = 0.0
              
              turn_lights_buzzer_state = not turn_lights_buzzer_state
            
    else:
        buzzer.duty_cycle = 0.0
        turn_lights_buzzer_state = True

    now = time.monotonic()
    if (now - power_switch_send_data_time_previous) > 0.5:
        power_switch_send_data_time_previous = now

        vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024
        power_switch.send_data()

    now = time.monotonic()
    if (now - buttons_time_previous) > 0.05:
        buttons_time_previous = now

        for index in range(nr_buttons):
            buttons[index].tick()
  
    # update time on RTC just once
    if update_date_time_once is False:
      now = time.monotonic()
      if (now - update_date_time_previous) > 2.0:
          update_date_time_once = True
          date_time_updated = rtc.update_date_time_from_wifi_ntp()
    
    # update time
    now = time.monotonic()
    if (now - date_time_previous) > 1.0:
        date_time_previous = now

        date_time = rtc.date_time()
        if date_time_updated is True:
          label_time.text = f'{date_time.tm_hour}:{date_time.tm_min:02}'
        elif date_time_updated is False:
          label_time.text = f''

    # sleep some time to save energy and avoid ESP32-S2 to overheat
    time.sleep(0.01)
