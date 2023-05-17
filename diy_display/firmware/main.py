import board
import buttons
import display
import motor_board
import system_data
import time
import displayio
from adafruit_display_text import label
import terminalio

import supervisor
supervisor.runtime.autoreload = False

########################################
# CONFIGURATIONS

# MAC Address value needed for the wireless communication with the EBike/EScooter board
mac_address_ebike_escooter_board = [0x68, 0xb6, 0xb3, 0x2b, 0xa7, 0x08]

# this display board MAC Address is = 0x48, 0x27, 0xe2, 0x4b, 0x37, 0x70
# found using:
# import wifi
# print([hex(i) for i in wifi.radio.mac_address])
########################################

buttons = buttons.Buttons(
        board.IO33, # POWER
        board.IO37, # UP
        board.IO35) # DOWN

displayObject = display.Display(
        board.IO7, # CLK pin
        board.IO9, # MOSI pin
        board.IO5, # chip select pin, not used but for some reason there is an error if chip_select is None
        board.IO12, # command pin
        board.IO11, # reset pin
        1000000) # spi clock frequency
display = displayObject.display

system_data = system_data.SystemData()

motor = motor_board.MotorBoard(
    system_data) # System data object to hold the EBike data

DISPLAY_WIDTH = 64  
DISPLAY_HEIGHT = 128
TEXT = "0"

def filter_motor_power(motor_power):

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
battery_voltage_area.anchor_point = (0.0, 0.0)
battery_voltage_area.anchored_position = (97, 0)
battery_voltage_area.scale = 1

label_x = 61
label_y = 10 + 16
label_1 = label.Label(terminalio.FONT, text=TEXT)
label_1.anchor_point = (1.0, 0.0)
label_1.anchored_position = (label_x, label_y)
label_1.scale = 2

label_x = 125
label_3 = label.Label(terminalio.FONT, text=TEXT)
label_3.anchor_point = (1.0, 0.0)
label_3.anchored_position = (label_x, label_y)
label_3.scale = 2

warning_area = label.Label(terminalio.FONT, text=TEXT)
warning_area.anchor_point = (0.0, 0.0)
warning_area.anchored_position = (2, 116)
warning_area.scale = 1

text_group = displayio.Group()
text_group.append(assist_level_area)
text_group.append(battery_voltage_area)
text_group.append(label_1)
# text_group.append(label_2)
text_group.append(label_3)
text_group.append(warning_area)

display.show(text_group)

assist_level = 0
assist_level_state = 0
now = time.monotonic()
assist_level_time_previous = now
display_time_previous = now
ebike_receive_data_time_previous = now
ebike_send_data_time_previous = now

battery_voltage_previous_x10 = 9999
battery_current_previous_x100 = 9999
motor_power_previous = 9999
motor_temperature_sensor_x10_previous = 9999
vesc_temperature_x10_previous = 9999
motor_speed_erpm_previous = 9999
brakes_are_active_previous = False
vesc_fault_code_previous = 9999

while True:
    now = time.monotonic()
    if (now - display_time_previous) > 0.1:
        display_time_previous = now

        if battery_voltage_previous_x10 != system_data.battery_voltage_x10:
            battery_voltage_previous_x10 = system_data.battery_voltage_x10
            battery_voltage = system_data.battery_voltage_x10 / 10.0
            battery_voltage_area.text = f"{battery_voltage:2.1f}v"

        if battery_current_previous_x100 != system_data.battery_current_x100:
            battery_current_previous_x100 = system_data.battery_current_x100
            
            # calculate the motor power
            system_data.motor_power = int((system_data.battery_voltage_x10 * system_data.battery_current_x100) / 1000.0)
            if system_data.motor_power < 0:
                system_data.motor_power = 0

            if motor_power_previous != system_data.motor_power:
                motor_power_previous = system_data.motor_power
                motor_power = filter_motor_power(system_data.motor_power)
                label_1.text = f"{system_data.motor_power:5}"
        
        # if motor_temperature_sensor_x10_previous != ebike_data.motor_temperature_sensor_x10:
        #     motor_temperature_sensor_x10_previous = ebike_data.motor_temperature_sensor_x10  
        #     label_2.text = str(f"{(ebike_data.motor_temperature_sensor_x10 / 10.0): 2.1f}")

        if motor_speed_erpm_previous != system_data.motor_speed_erpm:
            motor_speed_erpm_previous = system_data.motor_speed_erpm

            # Fiido Q1S original motor runs 45 ERPM for each 1 RPM
            # calculate the wheel speed
            wheel_radius = 0.165 # measured as 16.5cms
            perimeter = 6.28 * wheel_radius
            motor_rpm = system_data.motor_speed_erpm / 45.0
            speed = ((perimeter / 1000.0) * motor_rpm * 60)
            if speed < 0.1:
                speed = 0.0

            label_3.text = f"{speed:2.1f}"

    now = time.monotonic()
    if (now - ebike_receive_data_time_previous) > 0.1:
        ebike_receive_data_time_previous = now
        motor.process_data()

    now = time.monotonic()
    if (now - ebike_send_data_time_previous) > 0.1:
        ebike_send_data_time_previous = now
        motor.send_data()

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
    if (now - assist_level_time_previous) > 0.05:
        assist_level_time_previous = now

        # change assist level
        if assist_level_state == 1 and not buttons.up:
            assist_level_state = 0

        if assist_level_state == 2 and not buttons.down:
            assist_level_state = 0

        if assist_level < 20 and buttons.up and assist_level_state == 0:
            assist_level_state = 1
            assist_level += 1

        if assist_level > 0 and buttons.down and assist_level_state == 0:
            assist_level_state = 2
            assist_level -= 1

        system_data.assist_level = assist_level
        assist_level_area.text = str(assist_level)
