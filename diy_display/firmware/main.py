import board
import buttons
import display
import motor_board_espnow
import system_data
import time
import displayio
from adafruit_display_text import label
import terminalio
import power_switch_espnow
import wifi
import espnow as ESPNow

import supervisor
supervisor.runtime.autoreload = False

print("Starting Display")

########################################
# CONFIGURATIONS

# MAC Address value needed for the wireless communication
my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]
mac_address_power_switch_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf1]
mac_address_motor_board = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]
########################################

system_data = system_data.SystemData()

wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

_espnow = ESPNow.ESPNow()
motor = motor_board_espnow.MotorBoard(_espnow, mac_address_motor_board, system_data) # System data object to hold the EBike data
power_switch = power_switch_espnow.PowerSwitch(_espnow, mac_address_power_switch_board, system_data) # System data object to hold the EBike data

# this will try send data over ESPNow and if there is an error, will restart
system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
power_switch.update()
motor.send_data()

buttons = buttons.Buttons(
        board.IO33, # POWER
        board.IO37, # UP
        board.IO35) # DOWN

button_power_previous = False
button_power_long_press_previous = False
button_up_previous = False
button_down_previous = False

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


# screen 1
label_x = 10
label_y = 18
label_1 = label.Label(terminalio.FONT, text=TEXT)
label_1.anchor_point = (0.0, 0.0)
label_1.anchored_position = (label_x, label_y)
label_1.scale = 1
label_1.text = "Ready to power on"

screen1_group = displayio.Group()
screen1_group.append(label_1)
display.show(screen1_group)

time_previous = time.monotonic()
while True:
    now = time.monotonic()
    if (now - time_previous) > 0.05:
        time_previous = now

        buttons.tick()
        if buttons.power:
            system_data.system_power_state = True
            break


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

text_group = displayio.Group()
# text_group.append(assist_level_area)
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
power_switch_send_data_time_previous = now

battery_voltage_previous_x10 = 9999
battery_current_previous_x100 = 9999
motor_current_previous_x100 = 9999
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

        # calculate the motor power
        if system_data.motor_speed_erpm < 10:
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

            # Fiido Q1S original motor runs 45 ERPM for each 1 RPM
            # calculate the wheel speed
            wheel_radius = 0.165 # measured as 16.5cms
            perimeter = 6.28 * wheel_radius
            # motor_rpm = system_data.motor_speed_erpm / 45.0
            motor_rpm = system_data.motor_speed_erpm / 15.0
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

    now = time.monotonic()
    if (now - power_switch_send_data_time_previous) > 0.25:
        power_switch_send_data_time_previous = now

        system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
        power_switch.update()

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

        buttons.tick()

        button_up_changed = False
        if buttons.up != button_up_previous:
            button_up_previous = buttons.up
            button_up_changed = True

        button_down_changed = False
        if buttons.down != button_down_previous:
            button_down_previous = buttons.down

        if buttons.power != button_power_previous:
            button_power_previous = buttons.power

        if buttons.power_long_press != button_power_long_press_previous:
            button_power_long_press_previous = buttons.power_long_press
            system_data.system_power_state = False
            system_data.turn_off_relay = True

            label_x = 10
            label_y = 18
            label_1 = label.Label(terminalio.FONT, text=TEXT)
            label_1.anchor_point = (0.0, 0.0)
            label_1.anchored_position = (label_x, label_y)
            label_1.scale = 1
            label_1.text = "Shutting down"

            g = displayio.Group()
            g.append(label_1)
            display.show(g)

            while True:
                motor.send_data()
                
                system_data.display_communication_counter = (system_data.display_communication_counter + 1) % 1024
                power_switch.update()

                buttons.tick()
                if buttons.power_long_press != button_power_long_press_previous:
                    button_power_long_press_previous = buttons.power_long_press
                    import supervisor
                    supervisor.reload()
                
                time.sleep(0.1)

        if assist_level > 0 and button_down_changed:
            assist_level -= 1
        elif assist_level < 20 and button_up_changed:
            assist_level += 1

        system_data.assist_level = assist_level
        assist_level_area.text = str(assist_level)
