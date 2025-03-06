# Tested on a ESP32-S3-DevKitC-1-N8R2

import board
import time
import supervisor
import asyncio
import simpleio
from vars import Vars, MotorSingleDual, MotorControlScheme
from vesc import Vesc
import Brake
import throttle as Throttle
from microcontroller import watchdog
from watchdog import WatchDogMode
import os
import gc
import escooter_fiido_q1_s.display_espnow as DisplayESPnow
import wifi
from motor import MotorData, Motor
from configurations import cfg, front_motor_cfg, rear_motor_cfg

supervisor.runtime.autoreload = False

print()
print("Booting EBike/EScooter software")

# various variables
vars = Vars()

# setup radio MAC Adreess
wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(cfg.my_mac_address)
wifi.radio.start_ap(ssid="NO_SSID", channel=1)
wifi.radio.stop_ap()

# object to communicate with the display wireless by ESPNow
display = DisplayESPnow.Display(cfg.display_mac_address, vars)

# object to communicate with the VESC motor controllers
vesc = Vesc(rear_motor_cfg.uart_tx_pin, rear_motor_cfg.uart_rx_pin, rear_motor_cfg.uart_baudrate, vars)

# object to read the brake state
brake_sensor = Brake.Brake(board.IO12)

# if brakes are active at startup, block here
# this is needed for development, to help keep the motor and the UART disable
while brake_sensor.value:
    print('brake at start')
    time.sleep(1)

# object for left handle bar throttle
throttle_1 = Throttle.Throttle(
    board.IO11, # ADC pin for throttle
    min = cfg.throttle_1_adc_min, # min ADC value that throttle reads, plus some margin
    max = cfg.throttle_1_adc_max) # max ADC value that throttle reads, minus some margin

# object for right handle bar throttle
throttle_2 = Throttle.Throttle(
    board.IO10, # ADC pin for throttle
    min = cfg.throttle_2_adc_min, # min ADC value that throttle reads, plus some margin
    max = cfg.throttle_2_adc_max) # max ADC value that throttle reads, minus some margin

# object to control the motors
front_motor = Motor(vesc, front_motor_cfg)
rear_motor = Motor(vesc, rear_motor_cfg)
front_motor_data = MotorData()
rear_motor_data = MotorData()

async def task_vesc_refresh_data():
    while True:
        # ask for VESC latest data
        vesc.refresh_data()
        
        gc.collect()
        await asyncio.sleep(0.1)

async def task_display_refresh_data():
    while True:
        # send data to the display
        display.update()
        
        # received and process data from the display
        display.process_data()

        gc.collect()
        await asyncio.sleep(0.1)


def cruise_control(vars, throttle_value):
    button_long_press_state = vars.button_power_state & 0x0200
    
    # Set initial variables values
    if vars.cruise_control.state == 0:     
        vars.cruise_control.button_long_press_previous_state = button_long_press_state
        vars.cruise_control.state = 1
    
    # Wait for conditions to start cruise control
    if vars.cruise_control.state == 1:        
        if (button_long_press_state != vars.cruise_control.button_long_press_previous_state) and vars.wheel_speed > 4.0:
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            
            vars.cruise_control.throttle_value = throttle_value
            vars.cruise_control.state = 2
            
    # Cruise control is active
    if vars.cruise_control.state == 2:
        # Check for button pressed
        vars.cruise_control.button_pressed = False
        button_press_state = vars.button_power_state & 0x0100
        if button_press_state != vars.cruise_control.button_press_previous_state:
            vars.cruise_control.button_press_previous_state = button_press_state
            vars.cruise_control.button_pressed = True
        
        # Check for conditions to stop cruise control
        if vars.brakes_are_active or vars.cruise_control.button_pressed or throttle_value > (vars.cruise_control.throttle_value * 1.15):
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            vars.cruise_control.state = 1
        else:
            # Keep cruising...
            # overide the throttle value
            throttle_value = vars.cruise_control.throttle_value
        
    return throttle_value


# initialize here this variables - they hold values that will change real time depending on the wheel speed, like 'motor_target_current_limit_max' will be max at startup
motor_target_current_limit_max = motor_max_current_limit
motor_target_current_limit_min = motor_max_current_regen
battery_target_current_limit_max = battery_max_current_limit
battery_target_current_limit_min = battery_max_current_regen
async def task_control_motor():
    global vars
    global cfg
    global button_press_state_previous
    global front_motor
    global rear_motor
    global front_motor_data
    global rear_motor_data
    global throttle_1
    global throttle_2
    global brake_sensor
    
    # let's limit the wheel speed, so even in current control mode, the speed will be limited
    front_motor.set_motor_limit_speed(front_motor_data.motor_max_speed_limit)
    rear_motor.set_motor_limit_speed(rear_motor_data.motor_max_speed_limit)
    
    while True:
        ##########################################################################################
        # Throttle
        
        # read 1st and 2nd throttle, and use the max value of both
        throttle_value = max(throttle_1.value, throttle_2.value)

        # check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        throttle_adc_previous_value = throttle_1.adc_previous_value
        throttle_2_adc_previous_value = throttle_2.adc_previous_value
        if throttle_adc_previous_value > vars.throttle_1_adc_over_max_error or \
                throttle_2_adc_previous_value > cfg.throttle_2_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
            
            if throttle_adc_previous_value > vars.throttle_1_adc_over_max_error:
                message = f'throttle 1 value: {throttle_adc_previous_value} -- is over max, this can be dangerous!'
            else:
                message = f'throttle 2 value: {throttle_2_adc_previous_value} -- is over max, this can be dangerous!'
            raise Exception(message)
    
        # Apply cruise control
        # DISABLED UNTIL LIGHTS BUTTON IS NOT WORKING
        throttle_value = cruise_control(vars, throttle_value)
        
        # current
        vars.motor_target_current = simpleio.map_range(throttle_value, 0.0, 1000.0, 0.0, motor_target_current_limit_max)     
        
        # speed
        vars.motor_target_speed = simpleio.map_range(throttle_value, 0.0, 1000.0, 0.0, motor_erpm_max_speed_limit)
        ##########################################################################################

        ## Limit mins and max values
        # impose a min motor target value, as to much lower value will make the motor vibrate and not run (??)
        if vars.motor_target_current < motor_min_current_start: vars.motor_target_current = 0.0
        if vars.motor_target_current > motor_max_current_limit: vars.motor_target_current = motor_max_current_limit
        if vars.motor_target_current_regen < motor_max_current_regen: vars.motor_target_current_regen = motor_max_current_regen

        if vars.motor_target_speed < 500.0: vars.motor_target_speed = 0.0
        if vars.motor_target_speed > motor_erpm_max_speed_limit: vars.motor_target_speed = motor_erpm_max_speed_limit
            
        # limit very small and negative values
        if vars.motor_target_current < 1.0: vars.motor_target_current = 0.0
        if vars.motor_target_current_regen > -1.0: vars.motor_target_current_regen = 0.0
        
        # check if brakes are active
        vars.brakes_are_active = False
        if brake_sensor.value:
            vars.brakes_are_active = True
        
        # if motor state is disabled, set currents and speed to 0
        if vars.motor_enable_state == False:
            vars.motor_target_current = 0.0
            vars.motor_target_current_regen = 0
            vars.motor_target_speed = 0.0

        # elif motor_control_scheme == MotorControlScheme.SPEED:        
        motor.set_motor_current_limit_max(motor_target_current_limit_max)
        motor.set_motor_current_limit_min(motor_target_current_limit_min)
        motor.set_battery_current_limit_max(battery_target_current_limit_max)
        motor.set_battery_current_limit_min(battery_target_current_limit_min)
        if vars.brakes_are_active:
            motor.set_motor_speed_rpm(0)
        else:
            motor.set_motor_speed_rpm(vars.motor_target_speed)
            
        # we just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.02)
        
async def task_control_motor_limit_current():
    global front_motor_cfg
    global rear_motor_cfg
    global front_motor_data
    global rear_motor_data
    
    while True:
        ##########################################################################################
        front_motor_data.motor_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            front_motor_cfg.motor_current_limit_max_min_speed,
            front_motor_cfg.motor_current_limit_max_max,
            front_motor_cfg.motor_current_limit_max_min)
        
        rear_motor_data.motor_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            rear_motor_cfg.motor_current_limit_max_min_speed,
            rear_motor_cfg.motor_current_limit_max_max,
            rear_motor_cfg.motor_current_limit_max_min)
        
        
        front_motor_data.motor_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            front_motor_cfg.motor_current_limit_min_min_speed,
            front_motor_cfg.motor_current_limit_min_max,
            front_motor_cfg.motor_current_limit_mini_min)
        
        rear_motor_data.motor_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            rear_motor_cfg.motor_current_limit_min_min_speed,
            rear_motor_cfg.motor_current_limit_min_max,
            rear_motor_cfg.motor_current_limit_min_min)
        
        
        front_motor_data.battery_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            front_motor_cfg.battery_current_limit_max_min_speed,
            front_motor_cfg.battery_current_limit_max_max,
            front_motor_cfg.battery_current_limit_max_min)
        
        rear_motor_data.battery_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            rear_motor_cfg.battery_current_limit_max_min_speed,
            rear_motor_cfg.battery_current_limit_max_max,
            rear_motor_cfg.battery_current_limit_max_min)
        
        
        front_motor_data.battery_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            front_motor_cfg.battery_current_limit_min_min_speed,
            front_motor_cfg.battery_current_limit_min_max,
            front_motor_cfg.battery_current_limit_min_min)
        
        rear_motor_data.battery_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            rear_motor_cfg.battery_current_limit_min_min_speed,
            rear_motor_cfg.battery_current_limit_min_max,
            rear_motor_cfg.battery_current_limit_min_min)
        
        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.1)
        
wheel_speed_previous_motor_speed_erpm = 0
async def task_various():
    global front_motor_cfg
    global rear_motor_cfg
    global wheel_speed_previous_motor_speed_erpm
    global front_motor_data
    global rear_motor_data
    
    while True:

        # calculate the rear motor wheel speed
        if rear_motor_data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = rear_motor_data.speed_erpm
        
            # Fiido Q1S with installed Luneye motor 2000W
            # calculate the wheel speed
            wheel_radius = 0.165 # measured as 16.5cms
            perimeter = 6.28 * wheel_radius # 2*pi = 6.28
            motor_rpm = rear_motor_data.speed_erpm / rear_motor_cfg.poles_pair
            rear_motor_data.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60.0)

            if abs(rear_motor_data.wheel_speed < 2.0):
                rear_motor_data.wheel_speed = 0.0

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.1)

async def main():

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    watchdog.timeout = 1
    watchdog.mode = WatchDogMode.RESET

    vesc_refresh_data_task = asyncio.create_task(task_vesc_refresh_data())
    display_refresh_data_task = asyncio.create_task(task_display_refresh_data())
    control_motor_limit_current_task = asyncio.create_task(task_control_motor_limit_current())
    read_sensors_control_motor_task = asyncio.create_task(task_control_motor())
    various_task = asyncio.create_task(task_various())

    print("Starting EBike/EScooter")
    print()

    await asyncio.gather(vesc_refresh_data_task,
                        display_refresh_data_task,
                        control_motor_limit_current_task,
                        read_sensors_control_motor_task,
                        various_task)

asyncio.run(main())



