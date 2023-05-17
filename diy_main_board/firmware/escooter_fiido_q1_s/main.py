import board
import time
import supervisor
import simpleio
import asyncio
import system_data
import vesc
import simpleio
import brake
import throttle
import microcontroller
import watchdog
import gc
import escooter_fiido_q1_s.display_espnow as display_espnow

import supervisor
supervisor.runtime.autoreload = False

class MotorControlScheme:
    CURRENT = 0
    SPEED = 1

# while True:
#     pass

# Tested on a ESP32-S3-DevKitC-1-N8R2

###############################################
# OPTIONS

# Lunyee fast motor 12 inches (not the original Fiido Q1S motor) has 15 poles pair
motor_poles_pair = 15

# original Fiido Q1S 12 inches wheels are 305mm in diameter
wheel_circunference = 305.0

max_speed_limit = 20.0

# throttle value of original Fiido Q1S throttle
throttle_min = 16400 # this is a value that should be a bit superior than the min value, so if throttle is in rest position, motor will not run
throttle_max = 50540 # this is a value that should be a bit lower than the max value, so if throttle is at max position, the calculated value of throttle will be the max
throttle_over_max_error = 50800 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

motor_min_current_start = 5.0 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 40.0 # max value, be careful to not burn your motor

motor_control_scheme = MotorControlScheme.CURRENT
# motor_control_scheme = = MotorControlScheme.SPEED

# ramp up and down constants
if motor_control_scheme == MotorControlScheme.CURRENT:
    ramp_up_time = 0.002 # ram up time for each 1A
    ramp_down_time = 0.002 # ram down time for each 1A
elif motor_control_scheme == MotorControlScheme.SPEED:
    ramp_up_time = 0.0010 # ram up time for each 1 erpm
    ramp_down_time = 0.00005 # ram down time for each 1 erpm

# MAC Address value needed for the wireless communication with the display
display_mac_address = [0x48, 0x27, 0xe2, 0x50, 0x62, 0x78]
# get the display MAC address by running on the display:
# import wifi
# print([hex(i) for i in wifi.radio.mac_address])

###############################################

# watchdog, to reset the system if watchdog is not feed in time
wdt = microcontroller.watchdog

brake_sensor = brake.Brake(
   board.IO12) # brake sensor pin

throttle = throttle.Throttle(
    board.IO11, # ADC pin for throttle
    min = throttle_min, # min ADC value that throttle reads, plus some margin
    max = throttle_max) # max ADC value that throttle reads, minus some margin

system_data = system_data.SystemData()
vesc = vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    system_data)

display = display_espnow.Display(display_mac_address, system_data)

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

async def task_vesc_refresh_data():
    while True:
        # ask for VESC latest data
        vesc.refresh_data()
        gc.collect()

        display.update()
        gc.collect()

        # idle 250ms
        await asyncio.sleep(0.25)

motor_max_target_accumulated = 0
throttle_value_accumulated = 0

# TODO
max_speed_limit_in_erpm = ((max_speed_limit * 1000) / 3600)

async def task_control_motor():
    while True:
        ##########################################################################################
        # Throttle
        # map torque value
        if motor_control_scheme == MotorControlScheme.CURRENT:
            motor_max_target = motor_max_current_limit
        elif motor_control_scheme == MotorControlScheme.SPEED:
            # low pass filter battery voltage
            global motor_max_target_accumulated
            global max_speed_limit_in_erpm
            motor_max_target_accumulated -= ((int(motor_max_target_accumulated)) >> 7)
            motor_max_target_accumulated += max_speed_limit_in_erpm
            motor_max_target = (int(motor_max_target_accumulated)) >> 7
        else:
            raise Exception("invalid motor_control_scheme")

        # low pass filter torque sensor value to smooth it,
        # because the easy DIY hardware lacks such low pass filter on purpose
        global throttle_value_accumulated
        throttle_value_accumulated -= ((int(throttle_value_accumulated)) >> 2)
        throttle_value_accumulated += throttle.value
        throttle_value_filtered = (int(throttle_value_accumulated)) >> 2

        # check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        if throttle_value_filtered > throttle_over_max_error:
            raise Exception("throttle value is over max, this can be dangerous!")
    
        motor_target = simpleio.map_range(
            throttle_value_filtered,
            0, # min input
            1000, # max input
            0, # min output
            motor_max_target) # max output
        ##########################################################################################
    
        # impose a min motor target value, as to much lower value will make the motor vibrate and not run (??)
        if motor_control_scheme == MotorControlScheme.CURRENT:
            if motor_target < motor_min_current_start:
                motor_target = 0
        elif motor_control_scheme == MotorControlScheme.SPEED:
            if motor_target < 1000: # about 3.5 km/h
                motor_target = 0
    
        # apply ramp up / down factor: faster when ramp down
        if motor_target > system_data.motor_target:
            ramp_time = ramp_up_time
        else:
            ramp_time = ramp_down_time
            
        time_now = time.monotonic_ns()
        ramp_step = (time_now - system_data.ramp_last_time) / (ramp_time * 1000000000)
        system_data.ramp_last_time = time_now
        system_data.motor_target = utils_step_towards(system_data.motor_target, motor_target, ramp_step)

        # let's limit the value
        if motor_control_scheme == MotorControlScheme.CURRENT:
            if system_data.motor_target > motor_max_current_limit:
                system_data.motor_target = motor_max_current_limit
        # no limit for speed mode
            
        # limit very small and negative values
        if system_data.motor_target < 0.001:
            system_data.motor_target = 0

        # if brakes are active, set our motor target as zero
        if brake_sensor.value:
            system_data.motor_target = 0

        if motor_control_scheme == MotorControlScheme.CURRENT:
            vesc.set_motor_current_amps(system_data.motor_target)
        elif motor_control_scheme == MotorControlScheme.SPEED:
            # when speed is near zero, set motor current to 0 to release the motor
            if system_data.motor_target == 0 and system_data.motor_speed_erpm < 100:
                vesc.set_motor_current_amps(0)
            else:
                vesc.set_motor_speed_erpm(system_data.motor_target)

        # we just updated the motor target, so let's feed the watchdog to avoid a system reset
        wdt.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        
        # for debug only        
        # print()
        # print(ebike.brakes_value, ebike.throttle_value, int(ramp_step), int(motor_target), int(ebike.motor_target))

        # idle 20ms
        await asyncio.sleep(0.02)

async def task_various_0_5s():
    assert(wheel_circunference > 100), "wheel_circunference must be higher then 100mm (4 inches wheel)"
    
    while True:
        # # calculate wheel speed
        # # 15 pole pairs on Xiaomi M365 motor
        # # 1h --> 60 minutes
        # # 60 * 3.14 = 188.4
        # # 188.4 / 15 = 12,56
        # # mm to km --> 1000000 --> 0,00001256
        # system_data.wheel_speed = int(wheel_circunference * system_data.motor_speed_erpm * 0.00001256)
        # if system_data.wheel_speed > 99:
        #     system_data.wheel_speed = 99
        # elif system_data.wheel_speed < 0:
        #     system_data.wheel_speed = 0
        pass

        await asyncio.sleep(0.5)

async def main():

    print("starting")

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    wdt.timeout = 1
    wdt.mode = watchdog.WatchDogMode.RESET

    vesc_refresh_data_task = asyncio.create_task(task_vesc_refresh_data())
    read_sensors_control_motor_task = asyncio.create_task(task_control_motor())
    # various_0_5s_task = asyncio.create_task(task_various_0_5s())

    await asyncio.gather(vesc_refresh_data_task,
                        read_sensors_control_motor_task)
                        #  various_0_5s_task)

asyncio.run(main())
