import board
import time
import supervisor
import asyncio
import simpleio
import system_data as SystemData
import vesc as Vesc
import Brake
import throttle as Throttle
from microcontroller import watchdog
from watchdog import WatchDogMode
import gc
import escooter_fiido_q1_s.display_espnow as DisplayESPnow
import wifi

import supervisor
supervisor.runtime.autoreload = False

my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]
wifi.radio.mac_address = bytearray(my_mac_address)
wifi.radio.enabled = True

class MotorControlScheme:
    CURRENT = 0
    SPEED = 1
    SPEED_NO_REGEN = 2

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
throttle_adc_over_max_error = 51500 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

motor_min_current_start = 15.0 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 135.0 # max value, be careful to not burn your motor
motor_max_current_regen = -50.0 # max regen current

# To reduce motor temperature, motor current limits are higher at startup and low at higer speeds
# motor current limits will be adjusted on this values, depending on the speed
# like at startup will have 'motor_current_limit_max_max' and then will reduce linearly
# up to the 'motor_current_limit_max_min', when wheel speed is
# 'motor_current_limit_max_min_speed'
motor_current_limit_max_max = 135.0
motor_current_limit_max_min = 40.0
motor_current_limit_max_min_speed = 10.0
motor_current_limit_max_max_speed = 30.0

# this are the values for regen
motor_current_limit_min_min = -50.0
motor_current_limit_min_max = -30.0
motor_current_limit_min_max_speed = 30.0

# default as speed control
motor_control_scheme = MotorControlScheme.SPEED

# MAC Address value needed for the wireless communication with the display
display_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]

###############################################

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

sdata = SystemData.SystemData()

vesc = Vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    sdata)

throttle_lowpass_filter_state = None
def lowpass_filter(sample, filter_constant):
    global throttle_lowpass_filter_state

    # initialization
    if throttle_lowpass_filter_state is None:
        throttle_lowpass_filter_state = sample

    throttle_lowpass_filter_state = throttle_lowpass_filter_state - ((filter_constant) * ((throttle_lowpass_filter_state) - (sample)))
    
    return throttle_lowpass_filter_state

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
display = DisplayESPnow.Display(display_mac_address, sdata)

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
    
    button_long_press_state = sdata.button_power_state & 0x0200
    
    # Set initial variables values
    if cruise_control_state == 0:     
        cruise_control_button_long_press_previous_state = button_long_press_state
        cruise_control_state = 1
    
    # Wait for conditions to start cruise control
    if cruise_control_state == 1:        
        if (button_long_press_state != cruise_control_button_long_press_previous_state) and sdata.wheel_speed > 4.0:
            cruise_control_button_long_press_previous_state = button_long_press_state
            
            cruise_control_throttle_value = throttle_value
            cruise_control_state = 3
            
    if cruise_control_state == 2:
        cruise_control_button_press_previous_state = sdata.button_power_state & 0x0100
        cruise_control_state = 3
            
    # Cruise control is active
    if cruise_control_state == 3:
        # Check for button pressed
        cruise_control_button_pressed = False
        button_press_state = sdata.button_power_state & 0x0100
        if button_press_state != cruise_control_button_press_previous_state:
            cruise_control_button_press_previous_state = button_press_state
            cruise_control_button_pressed = True
        
        # Check for conditions to stop cruise control
        if sdata.brakes_are_active or cruise_control_button_pressed or throttle_value > (cruise_control_throttle_value * 1.15):
            cruise_control_button_long_press_previous_state = button_long_press_state
            cruise_control_state = 1
        else:
            # Keep cruising...
            # overide the throttle value
            throttle_value = cruise_control_throttle_value
        
    return throttle_value

# initialize here this variables - they hold values that will change real time depending on the wheel speed, like 'motor_target_current_limit_max' will be max at startup
motor_target_current_limit_max = motor_max_current_limit
motor_target_current_limit_min = motor_max_current_regen
button_press_state_previous = True
async def task_control_motor():
    global motor_target_current_limit_max
    global motor_target_current_limit_min
    global button_press_state_previous
    global motor_control_scheme
    
    # let's limit the wheel speed, so even in current control mode, the speed will be limited
    vesc.set_motor_limit_speed(motor_max_speed_limit)
    
    while True:
        ##########################################################################################
        # Throttle
        # map torque value

        # low pass filter torque sensor value to smooth it,
        # because the easy DIY hardware lacks such low pass filter on purpose
        # throttle_value_filtered = lowpass_filter(throttle.value, 0.02)
        # if throttle_value_filtered < 0.01:
        #   throttle_value_filtered = 0
        throttle_value_filtered = throttle.value
  
        # check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        throttle_adc_previous_value = throttle.adc_previous_value
        if throttle_adc_previous_value > throttle_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            vesc.set_motor_current_amps(0)
            vesc.set_motor_current_amps(0)
            vesc.set_motor_current_amps(0)
            raise Exception(f'throttle value: {throttle_adc_previous_value} -- is over max, this can be dangerous!')
    
        # Apply cruise control
        throttle_value_filtered = cruise_control(throttle_value_filtered)
        
        # If button was pressed, switch the motor_control_scheme
        button_press_state = True if sdata.button_power_state & 0x0100 else False
        if button_press_state != button_press_state_previous:
            button_press_state_previous = button_press_state
            
            if motor_control_scheme == MotorControlScheme.CURRENT:
                motor_control_scheme = MotorControlScheme.SPEED
            elif motor_control_scheme == MotorControlScheme.SPEED:
                motor_control_scheme = MotorControlScheme.SPEED_NO_REGEN
            elif motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:
                motor_control_scheme = MotorControlScheme.CURRENT
    
        sdata.motor_target_current = simpleio.map_range(
            throttle_value_filtered,
            0.0,
            1000.0,
            0.0,
            motor_target_current_limit_max)
        
        sdata.motor_target_current_regen = motor_target_current_limit_min
        
        sdata.motor_target_speed = simpleio.map_range(
            throttle_value_filtered,
            0.0,
            1000.0,
            0.0,
            motor_erpm_max_speed_limit)
        ##########################################################################################

        # impose a min motor target value, as to much lower value will make the motor vibrate and not run (??)
        if sdata.motor_target_current < motor_min_current_start:
            sdata.motor_target_current = 0.0

        if sdata.motor_target_speed < 500.0:
            sdata.motor_target_speed = 0.0
    
        # let's limit the value
        if sdata.motor_target_current > motor_max_current_limit:
            sdata.motor_target_current = motor_max_current_limit
            
        if sdata.motor_target_current_regen < motor_max_current_regen:
            sdata.motor_target_current_regen = motor_max_current_regen

        if sdata.motor_target_speed > motor_erpm_max_speed_limit:
            sdata.motor_target_speed = motor_erpm_max_speed_limit
            
        # limit very small and negative values
        if sdata.motor_target_current < 1.0:
            sdata.motor_target_current = 0.0

        if sdata.motor_target_speed < 500.0: # 2 kms/h
            sdata.motor_target_speed = 0.0

        # if brakes are active, set values to try stop the wheel
        if brake_sensor.value:
            sdata.brakes_are_active = True
            
            # set specific motor current when braking
            if motor_control_scheme == MotorControlScheme.CURRENT:
                if sdata.wheel_speed > 5.0:
                    sdata.motor_target_current = sdata.motor_target_current_regen
                else:
                    # avoid making the wheel / motor rotate backwards
                    sdata.motor_target_current = 0.0
                    
            # set specific motor speed when braking
            else: # motor_control_scheme == MotorControlScheme.SPEED or \
                # motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:
                    sdata.motor_target_speed = 0.0
                
        # brakes not active    
        else:
            sdata.brakes_are_active = False
        
        # in SPEED_NO_REGEN mode, set motor_current_limit_min to 0 to disable regen
        if motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:
            if brake_sensor.value:
                vesc.set_motor_current_limit_min(sdata.motor_target_current_regen)
            else:
                vesc.set_motor_current_limit_min(0.0)

        # if motor state is off, set our motor target as zero
        if sdata.motor_enable_state == False:
            sdata.motor_target_current = 0.0
            sdata.motor_target_speed = 0.0

        if motor_control_scheme == MotorControlScheme.CURRENT:
            vesc.set_motor_current_amps(sdata.motor_target_current)
        else: # motor_control_scheme == MotorControlScheme.SPEED or \
                # motor_control_scheme == MotorControlScheme.SPEED_NO_REGEN:
            vesc.set_motor_speed_rpm(sdata.motor_target_speed)

        # we just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 20ms
        await asyncio.sleep(0.02)
        
async def task_control_motor_limit_current():
    global motor_target_current_limit_max
    global motor_target_current_limit_min
    
    while True:
        ##########################################################################################
        motor_target_current_limit_max = simpleio.map_range(
            sdata.wheel_speed,
            motor_current_limit_max_min_speed,
            motor_current_limit_max_max_speed,
            motor_current_limit_max_max,
            motor_current_limit_max_min)
        
        motor_target_current_limit_min = simpleio.map_range(
            sdata.wheel_speed,
            motor_current_limit_max_min_speed,
            motor_current_limit_max_max_speed,
            motor_current_limit_min_min,
            motor_current_limit_min_max)
        
        vesc.set_motor_current_limit_max(motor_target_current_limit_max)
        
        # In SPEED_NO_REGEN mode, the motor_current_limit_min should not be set here
        if motor_control_scheme != MotorControlScheme.SPEED_NO_REGEN:
            vesc.set_motor_current_limit_min(motor_target_current_limit_min)

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 1 second
        await asyncio.sleep(1.0)

wheel_speed_previous_motor_speed_erpm = 0
async def task_various_0_5s():
    global wheel_speed_previous_motor_speed_erpm
    
    while True:
        if sdata.motor_speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = sdata.motor_speed_erpm
        
            # Fiido Q1S with installed Luneye motor 2000W
            # calculate the wheel speed
            wheel_radius = 0.165 # measured as 16.5cms
            perimeter = 6.28 * wheel_radius # 2*pi = 6.28
            motor_rpm = sdata.motor_speed_erpm / motor_poles_pair
            sdata.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60)

            if abs(sdata.wheel_speed < 3.5):
                sdata.wheel_speed = 0.0

        await asyncio.sleep(0.5)

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
    various_0_5s_task = asyncio.create_task(task_various_0_5s())

    await asyncio.gather(vesc_refresh_data_task,
                        display_refresh_data_task,
                        control_motor_limit_current_task,
                        read_sensors_control_motor_task,
                        various_0_5s_task)

asyncio.run(main())

