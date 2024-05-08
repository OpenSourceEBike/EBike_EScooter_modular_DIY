import board
import time
import supervisor
import asyncio
import simpleio
import vars as Vars
import vesc as Vesc
import Brake
import throttle as Throttle
from microcontroller import watchdog
from watchdog import WatchDogMode
import os
import gc
import escooter_fiido_q1_s.display_espnow as DisplayESPnow
import wifi
import escooter_fiido_q1_s.motor as motor

import supervisor
supervisor.runtime.autoreload = False

# MAC Address value needed for the wireless communication
my_dhcp_host_name = 'Mainboard-EScooter-CAS' # no spaces, no underscores, max 30 chars
my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]

wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.hostname = my_dhcp_host_name
wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))

class MotorSingleDual:
    SINGLE = 0
    DUAL = 1   

class MotorControlScheme:
    SPEED = 0
    SPEED_NO_REGEN = 1
    # CURRENT = 2
 
# Tested on a ESP32-S3-DevKitC-1-N8R2

###############################################
# OPTIONS

# Lunyee 2000W motor 12 inches (not the original Fiido Q1S motor) has 15 poles pair
motor_poles_pair = 15

# max wheel speed in ERPM
# tire diameter: 0.33 meters
# tire RPM: 884
# motor poles: 15
# motor ERPM: 13263 to get 55kms/h wheel speed
motor_erpm_max_speed_limit = 13263 # 55kms/h
motor_max_speed_limit = 16 # don't know why need to be 16 to be limited to 55 # 55kms/h

# throttle value of original Fiido Q1S throttle
throttle_adc_min = 16400 # this is a value that should be a bit superior than the min value, so if throttle is in rest position, motor will not run
throttle_adc_max = 50540 # this is a value that should be a bit lower than the max value, so if throttle is at max position, the calculated value of throttle will be the max
throttle_adc_over_max_error = 54500 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

throttle_regen_adc_min = 18000
throttle_regen_adc_max = 49000
throttle_regen_adc_over_max_error = 54500

motor_max_current_limit = 135.0 # max value, be careful to not burn your motor
motor_min_current_start = 1.0 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_regen = -80.0 # max regen current

battery_max_current_limit = 31.0 # about 2200W at 72V
battery_max_current_regen = -14.0 # about 1000W at 72V

# To reduce motor temperature, motor current limits are higher at startup and low at higer speeds
# motor current limits will be adjusted on this values, depending on the speed
# like at startup will have 'motor_current_limit_max_max' and then will reduce linearly
# up to the 'motor_current_limit_max_min', when wheel speed is
# 'motor_current_limit_max_min_speed'
motor_current_limit_max_max = 120.0
motor_current_limit_max_min = 60.0
motor_current_limit_max_min_speed = 25.0

# this are the values for regen
motor_current_limit_min_min = -80.0
motor_current_limit_min_max = -80.0
motor_current_limit_min_max_speed = 25.0

## Battery currents
battery_current_limit_max_max = 31.0 # about 2200W at 72V
battery_current_limit_max_min = 27.0 # about 20% less
battery_current_limit_max_min_speed = 25.0

# this are the values for regen
battery_current_limit_min_min = -14.0
battery_current_limit_min_max = -12.0 # about xx% less
battery_current_limit_min_max_speed = 25.0

# Single or Dual motor setup
# motor_single_dual = MotorSingleDual.SINGLE
motor_single_dual = MotorSingleDual.DUAL
motor_1_dual_factor = 0.6
motor_2_dual_factor = 0.6
motor_can_id = 101

# default motor control scheme
motor_control_scheme = MotorControlScheme.SPEED

# MAC Address value needed for the wireless communication with the display
display_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]

###############################################

MotorControlScheme_len = len([attr for attr in dir(MotorControlScheme) if not attr.startswith('__')])

brake_sensor = Brake.Brake(
   board.IO12) # brake sensor pin

# if brakes are active at startup, block here
# this is needed for development, to help keep the motor and the UART disable
while brake_sensor.value:
    print('brake at start')
    time.sleep(1)

throttle = Throttle.Throttle(
    board.IO11, # ADC pin for throttle
    min = throttle_adc_min, # min ADC value that throttle reads, plus some margin
    max = throttle_adc_max) # max ADC value that throttle reads, minus some margin

throttle_regen = Throttle.Throttle(
    board.IO10, # ADC pin for throttle
    min = throttle_regen_adc_min, # min ADC value that throttle reads, plus some margin
    max = throttle_regen_adc_max) # max ADC value that throttle reads, minus some margin

vars = Vars.Vars()

vesc = Vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    vars)

if motor_single_dual == MotorSingleDual.SINGLE:
    motor = motor.Motor(
        vesc,
        False) # this is a single motor
else:
    motor = motor.Motor(
        vesc,
        True, # this is a dual motor
        motor_1_dual_factor,
        motor_2_dual_factor,
        motor_can_id)

def utils_step_towards(current_value, target_value, step):
    """ Move current_value towards the target_value, by increasing / decreasing by step
    """
    value = current_value

    if current_value < target_value:
        if (current_value + step) < target_value:
            value += step
        else:
            value = target_value
    
    elif current_value > target_value:
        if (current_value - step) > target_value:
            value -= step
        else:
            value = target_value

    return value

# don't know why, but if this objects related to ESPNow are started earlier, system will enter safemode
display = DisplayESPnow.Display(display_mac_address, vars)

async def task_vesc_refresh_data():
    while True:
        # ask for VESC latest data
        vesc.refresh_data()
        gc.collect()

        # idle 100ms
        await asyncio.sleep(0.1)

async def task_display_refresh_data():
    while True:
        # send data to the display
        display.update()
        gc.collect()
        
        # process received data from the display
        display.process_data()
        gc.collect()

        # idle 100ms
        await asyncio.sleep(0.1)

cruise_control_state = 0
cruise_control_button_long_press_previous_state = 0
cruise_control_button_press_previous_state = 0
cruise_control_throttle_value = 0
def cruise_control(throttle_value):
    global cruise_control_state
    global cruise_control_button_long_press_previous_state
    global cruise_control_button_press_previous_state
    global cruise_control_throttle_value
    
    button_long_press_state = vars.button_power_state & 0x0200
    
    # Set initial variables values
    if cruise_control_state == 0:     
        cruise_control_button_long_press_previous_state = button_long_press_state
        cruise_control_state = 1
    
    # Wait for conditions to start cruise control
    if cruise_control_state == 1:        
        if (button_long_press_state != cruise_control_button_long_press_previous_state) and vars.wheel_speed > 4.0:
            cruise_control_button_long_press_previous_state = button_long_press_state
            
            cruise_control_throttle_value = throttle_value
            cruise_control_state = 2
            
    # Cruise control is active
    if cruise_control_state == 2:
        # Check for button pressed
        cruise_control_button_pressed = False
        button_press_state = vars.button_power_state & 0x0100
        if button_press_state != cruise_control_button_press_previous_state:
            cruise_control_button_press_previous_state = button_press_state
            cruise_control_button_pressed = True
        
        # Check for conditions to stop cruise control
        if vars.brakes_are_active or cruise_control_button_pressed or throttle_value > (cruise_control_throttle_value * 1.15):
            cruise_control_button_long_press_previous_state = button_long_press_state
            cruise_control_state = 1
        else:
            # Keep cruising...
            # overide the throttle value
            throttle_value = cruise_control_throttle_value
        
    return throttle_value

button_press_state_previous = False
def process_motor_control_scheme(motor_control_scheme):
    global button_press_state_previous
    
    button_press_state = True if vars.button_power_state & 0x0100 else False
    if button_press_state != button_press_state_previous:
        button_press_state_previous = button_press_state
        
        if motor_control_scheme < (MotorControlScheme_len - 1):
            motor_control_scheme += 1
        else:
            motor_control_scheme = 0
                        
        # # force speed limit
        # if motor_control_scheme == MotorControlScheme.CURRENT:
        #     motor.set_motor_limit_speed(motor_max_speed_limit)
            
        print(f'motor_control_scheme: {motor_control_scheme}')
            
    return motor_control_scheme 

# initialize here this variables - they hold values that will change real time depending on the wheel speed, like 'motor_target_current_limit_max' will be max at startup
motor_target_current_limit_max = motor_max_current_limit
motor_target_current_limit_min = motor_max_current_regen
battery_target_current_limit_max = battery_max_current_limit
battery_target_current_limit_min = battery_max_current_regen
async def task_control_motor():
    global motor_target_current_limit_max
    global motor_target_current_limit_min
    global battery_target_current_limit_max
    global battery_target_current_limit_min
    global button_press_state_previous
    global motor_control_scheme
    
    # let's limit the wheel speed, so even in current control mode, the speed will be limited
    motor.set_motor_limit_speed(motor_max_speed_limit)
    
    while True:
        
        # See if we want to switch the motor_control_scheme
        motor_control_scheme = process_motor_control_scheme(motor_control_scheme)

        ##########################################################################################
        # Throttle
        
        throttle_value = throttle.value
        throttle_regen_value = throttle_regen.value

        # check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        throttle_adc_previous_value = throttle.adc_previous_value
        throttle_regen_adc_previous_value = throttle_regen.adc_previous_value
        if throttle_adc_previous_value > throttle_adc_over_max_error or \
                throttle_regen_adc_previous_value > throttle_regen_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            motor.set_motor_current_amps(0)
            motor.set_motor_current_amps(0)
            motor.set_motor_current_amps(0)
            
            if throttle_adc_previous_value > throttle_adc_over_max_error:
                message = f'throttle value: {throttle_adc_previous_value} -- is over max, this can be dangerous!'
            else:
                message = f'throttle regen value: {throttle_regen_adc_previous_value} -- is over max, this can be dangerous!'
            raise Exception(message)
    
        # Apply cruise control
        throttle_value = cruise_control(throttle_value)
        
        # current
        vars.motor_target_current = simpleio.map_range(throttle_value, 0.0, 1000.0, 0.0, motor_target_current_limit_max)

        # brake regen current
        if motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:
            vars.motor_target_current_regen = simpleio.map_range(throttle_regen_value, 0.0, 1000.0, 0.0, motor_target_current_limit_min)
        else:
            vars.motor_target_current_regen = motor_target_current_limit_min        
        
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
            
        # # apply the currents and speed values
        # if motor_control_scheme == MotorControlScheme.CURRENT:
        #     motor.set_motor_current_limit_max(motor_target_current_limit_max)
        #     motor.set_motor_current_limit_min(motor_target_current_limit_min)
        #     motor.set_battery_current_limit_max(battery_target_current_limit_max)
        #     motor.set_battery_current_limit_min(battery_target_current_limit_min)
            
        #     if vars.brakes_are_active:                
        #         motor.set_motor_current_brake_amps(0)
        #     else:
        #         motor.set_motor_current_amps(vars.motor_target_current)

        elif motor_control_scheme == MotorControlScheme.SPEED:            
            motor.set_motor_current_limit_max(motor_target_current_limit_max)
            motor.set_motor_current_limit_min(motor_target_current_limit_min)
            motor.set_battery_current_limit_max(battery_target_current_limit_max)
            motor.set_battery_current_limit_min(battery_target_current_limit_min)
            if vars.brakes_are_active:
                motor.set_motor_speed_rpm(0)
            else:
                motor.set_motor_speed_rpm(vars.motor_target_speed)
            
        elif motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:        
            motor.set_motor_current_limit_max(motor_target_current_limit_max)
            motor.set_battery_current_limit_max(battery_target_current_limit_max)
            motor.set_battery_current_limit_min(battery_target_current_limit_min)
        
            if vars.brakes_are_active:
                motor.set_motor_current_limit_min(motor_target_current_limit_min)
                motor.set_motor_speed_rpm(0)
            else:
                if (vars.motor_target_current_regen >= 0):
                    motor.set_motor_current_limit_min(0)
                    motor.set_motor_speed_rpm(vars.motor_target_speed)
                else:
                    motor.set_motor_current_limit_min(vars.motor_target_current_regen)
                    motor.set_motor_speed_rpm(0)
            
        # we just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 20ms
        await asyncio.sleep(0.02)
        
async def task_control_motor_limit_current():
    global motor_target_current_limit_max
    global motor_target_current_limit_min
    global battery_target_current_limit_max
    global battery_target_current_limit_min
    
    while True:
        ##########################################################################################
        motor_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            motor_current_limit_max_min_speed,
            motor_current_limit_max_max,
            motor_current_limit_max_min)
        
        motor_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            motor_current_limit_min_max_speed,
            motor_current_limit_min_min,
            motor_current_limit_min_max)
        
        battery_target_current_limit_max = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            battery_current_limit_max_min_speed,
            battery_current_limit_max_max,
            battery_current_limit_max_min)
        
        battery_target_current_limit_min = simpleio.map_range(
            vars.wheel_speed,
            5.0,
            battery_current_limit_min_max_speed,
            battery_current_limit_min_min,
            battery_current_limit_min_max)
        
        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 100 ms
        await asyncio.sleep(0.1)
        
wheel_speed_previous_motor_speed_erpm = 0
async def task_various():
    global wheel_speed_previous_motor_speed_erpm
    
    while True:
        if vars.motor_speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = vars.motor_speed_erpm
        
            # Fiido Q1S with installed Luneye motor 2000W
            # calculate the wheel speed
            wheel_radius = 0.165 # measured as 16.5cms
            perimeter = 6.28 * wheel_radius # 2*pi = 6.28
            motor_rpm = vars.motor_speed_erpm / motor_poles_pair
            vars.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60.0)

            if abs(vars.wheel_speed < 2.0):
                vars.wheel_speed = 0.0

        await asyncio.sleep(0.1)

async def main():

    print("Starting EBike/EScooter")

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    watchdog.timeout = 1
    watchdog.mode = WatchDogMode.RESET

    vesc_refresh_data_task = asyncio.create_task(task_vesc_refresh_data())
    display_refresh_data_task = asyncio.create_task(task_display_refresh_data())
    control_motor_limit_current_task = asyncio.create_task(task_control_motor_limit_current())
    read_sensors_control_motor_task = asyncio.create_task(task_control_motor())
    various_task = asyncio.create_task(task_various())

    await asyncio.gather(vesc_refresh_data_task,
                        display_refresh_data_task,
                        control_motor_limit_current_task,
                        read_sensors_control_motor_task,
                        various_task)

asyncio.run(main())



