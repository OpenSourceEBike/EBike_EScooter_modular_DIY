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

wifi.radio.enabled = True
my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]
wifi.radio.mac_address = bytearray(my_mac_address)

class MotorControlScheme:
    CURRENT = 0
    SPEED_CURRENT = 1

# while True:
#     pass

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
motor_max_speed_limit = 13263 # 55kms/h

# throttle value of original Fiido Q1S throttle
throttle_adc_min = 16400 # this is a value that should be a bit superior than the min value, so if throttle is in rest position, motor will not run
throttle_adc_max = 50540 # this is a value that should be a bit lower than the max value, so if throttle is at max position, the calculated value of throttle will be the max
throttle_adc_over_max_error = 51500 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

motor_min_current_start = 10.0 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 150.0 # max value, be careful to not burn your motor

# motor_control_scheme = MotorControlScheme.CURRENT
motor_control_scheme = MotorControlScheme.SPEED_CURRENT

# ramp up and down constants
current_ramp_up_time = 0.00001 # ram up time for each 1A
current_ramp_down_time = 0.00001 # ram down time for each 1A
speed_ramp_up_time = 0.00001 # ram up time for each 1 erpm
speed_ramp_down_time = 0.00001 # ram down time for each 1 erpm

# MAC Address value needed for the wireless communication with the display
display_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]

###############################################

brake_sensor = Brake.Brake(
   board.IO12) # brake sensor pin

# if brakes are active at startup, block here
# this is needed for development, to help keep the motor and the UART disable
# if brake_sensor.value:
#     while True:
#         print('brake at start')
#         time.sleep(1)
#         pass

throttle = Throttle.Throttle(
    board.IO11, # ADC pin for throttle
    min = throttle_adc_min, # min ADC value that throttle reads, plus some margin
    max = throttle_adc_max) # max ADC value that throttle reads, minus some margin

system_data = SystemData.SystemData()

vesc = Vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    system_data)

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
display = DisplayESPnow.Display(display_mac_address, system_data)

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
    
    button_long_press_state = system_data.button_power_state & 0x0200
    
    # Set initial variables values
    if cruise_control_state == 0:     
        cruise_control_button_long_press_previous_state = button_long_press_state
        cruise_control_state = 1
    
    # Wait for conditions to start cruise control
    if cruise_control_state == 1:        
        if (button_long_press_state != cruise_control_button_long_press_previous_state) and system_data.wheel_speed > 4.0:
            cruise_control_button_long_press_previous_state = button_long_press_state
            
            cruise_control_throttle_value = throttle_value
            cruise_control_state = 3
            
    if cruise_control_state == 2:
        cruise_control_button_press_previous_state = system_data.button_power_state & 0x0100
        cruise_control_state = 3
            
    # Cruise control is active
    if cruise_control_state == 3:
        # Check for button pressed
        cruise_control_button_pressed = False
        button_press_state = system_data.button_power_state & 0x0100
        if button_press_state != cruise_control_button_press_previous_state:
            cruise_control_button_press_previous_state = button_press_state
            cruise_control_button_pressed = True
        
        # Check for conditions to stop cruise control
        if system_data.brakes_are_active or cruise_control_button_pressed or throttle_value > (cruise_control_throttle_value * 1.15):
            cruise_control_button_long_press_previous_state = button_long_press_state
            cruise_control_state = 1
        else:
            # Keep cruising...
            # overide the throttle value
            throttle_value = cruise_control_throttle_value
        
    return throttle_value

async def task_control_motor():
    while True:
        ##########################################################################################
        # Throttle
        # map torque value
        motor_max_current_target = motor_max_current_limit
        motor_max_speed_target = motor_max_speed_limit

        # low pass filter torque sensor value to smooth it,
        # because the easy DIY hardware lacks such low pass filter on purpose
        #throttle_value_filtered = lowpass_filter(throttle.value, 0.25)
        #if throttle_value_filtered < 1.0:
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
            print(f"throttle_adc_previous_value: {throttle_adc_previous_value}")
            raise Exception("throttle value is over max, this can be dangerous!")
    
        # Apply cruise control
        throttle_value_filtered = cruise_control(throttle_value_filtered)
    
        motor_target_current = simpleio.map_range(
            throttle_value_filtered,
            0.0, # min input
            1000.0, # max input
            motor_min_current_start, # min output
            motor_max_current_target) # max output
        
        motor_target_speed = simpleio.map_range(
            throttle_value_filtered,
            0.0, # min input
            1000.0, # max input
            500.0, # min output
            motor_max_speed_target) # max output
        ##########################################################################################

        # impose a min motor target value, as to much lower value will make the motor vibrate and not run (??)
        if motor_target_current < (motor_min_current_start + 1):
            motor_target_current = 0.0

        if motor_target_speed < 500.0:
            motor_target_speed = 0.0
    
        # apply ramp up / down factor: faster when ramp down
        if motor_target_current > system_data.motor_target_current:
            ramp_time_current = current_ramp_up_time
        else:
            ramp_time_current = current_ramp_down_time

        if motor_target_speed > system_data.motor_target_speed:
            ramp_time_speed = speed_ramp_up_time
        else:
            ramp_time_speed = speed_ramp_down_time
            
        time_now = time.monotonic_ns()
        ramp_step = (time_now - system_data.ramp_current_last_time) / (ramp_time_current * 40_000_000)
        system_data.ramp_current_last_time = time_now
        system_data.motor_target_current = utils_step_towards(system_data.motor_target_current, motor_target_current, ramp_step)

        time_now = time.monotonic_ns()
        ramp_step = (time_now - system_data.ramp_speed_last_time) / (ramp_time_speed * 40_000_000)
        system_data.ramp_speed_last_time = time_now
        system_data.motor_target_speed = utils_step_towards(system_data.motor_target_speed, motor_target_speed, ramp_step)

        # let's limit the value
        if system_data.motor_target_current > motor_max_current_limit:
            system_data.motor_target_current = motor_max_current_limit

        if system_data.motor_target_speed > motor_max_speed_limit:
            system_data.motor_target_speed = motor_max_speed_limit
            
        # limit very small and negative values
        if system_data.motor_target_current < 1.0:
            system_data.motor_target_current = 0.0

        if system_data.motor_target_speed < 500.0: # 2 kms/h
            system_data.motor_target_speed = 0.0

        # if brakes are active, set our motor target as zero
        if brake_sensor.value:
            system_data.motor_target_current = 0.0
            system_data.motor_target_speed = 0.0
            system_data.brakes_are_active = True
        else:
            system_data.brakes_are_active = False

        # if motor state is off, set our motor target as zero
        if system_data.motor_enable_state == False:
            system_data.motor_target_current = 0.0
            system_data.motor_target_speed = 0.0

        if motor_control_scheme == MotorControlScheme.CURRENT:
            vesc.set_motor_current_amps(system_data.motor_target_current)
        elif motor_control_scheme == MotorControlScheme.SPEED_CURRENT:
            vesc.set_motor_speed_rpm(system_data.motor_target_speed)

        # we just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 20ms
        await asyncio.sleep(0.02)
        
async def task_control_motor_limit_current():
    while True:
        ##########################################################################################
        motor_target_current_limit_max = simpleio.map_range(
            system_data.wheel_speed,
            0.0, # min input
            35.0, # max input
            135, # min output
            50) # max output
        
        motor_target_current_limit_min = -1.0 * simpleio.map_range(
            system_data.wheel_speed,
            0.0, # min input
            35.0, # max input
            70, # min output
            50) # max output
        
        vesc.set_motor_current_limit_max(motor_target_current_limit_max)
        vesc.set_motor_current_limit_min(motor_target_current_limit_min)

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython

        # idle 1 second
        await asyncio.sleep(1.0)

wheel_speed_previous_motor_speed_erpm = 0
async def task_various_0_5s():
    global wheel_speed_previous_motor_speed_erpm
    
    while True:
        if system_data.motor_speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = system_data.motor_speed_erpm
        
            if system_data.motor_speed_erpm > 150:
                # Fiido Q1S with installed Luneye motor 2000W
                # calculate the wheel speed
                wheel_radius = 0.165 # measured as 16.5cms
                perimeter = 6.28 * wheel_radius # 2*pi = 6.28
                motor_rpm = system_data.motor_speed_erpm / motor_poles_pair
                system_data.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60)

            else:
                system_data.wheel_speed = 0.0

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

