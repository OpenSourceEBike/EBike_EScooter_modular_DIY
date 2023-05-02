import board
import time
import supervisor
import simpleio
import asyncio
import ebike_data
import vesc
import m365_dashboard as m365_dashboard
import simpleio

import supervisor
# supervisor.runtime.autoreload = False

# Tested on a ESP32-S3-DevKitC-1-N8R2

###############################################
# OPTIONS

# original M365 8.5 inches wheels are 215mm in diameter
# M365 10 inches wheels are 245mm in diameter
wheel_circunference = 245.0

throttle_max = 190
throttle_min = 45

motor_min_current_start = 1.5 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 40.0 # max value, be carefull to not burn your motor

#motor_control_scheme = 'current'
motor_control_scheme = 'speed'

# ramp up and down constants
if motor_control_scheme == 'current':
    ramp_up_time = 0.05 # ram up time for each 1A
    ramp_down_time = 0.05 # ram down time for each 1A
elif motor_control_scheme == 'speed':
    ramp_up_time = 0.0001 # ram up time for each 1 erpm
    ramp_down_time = 0.00005 # ram down time for each 1 erpm

xiaomi_m365_rear_lights_always_on = True

###############################################

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

ebike = ebike_data.EBike()
vesc = vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    ebike) #VESC data object to hold the VESC data
vesc.set_motor_current_brake_amps(8)

dashboard = m365_dashboard.M365_dashboard(
    board.IO12, # UART TX pin
    board.IO11, # UART RX pin
    board.IO10, # dashboard button
    ebike,
    xiaomi_m365_rear_lights_always_on)

async def task_vesc_heartbeat():
    while True:
        # VESC heart beat must be sent more frequently than 1 second, otherwise the motor will stop
        vesc.send_heart_beat()
        
        # ask for VESC latest data
        vesc.refresh_data()

        # idle 500ms
        await asyncio.sleep(0.5)

async def task_dashboard():
    while True:
        dashboard.process_data()

        await asyncio.sleep(0.02)

motor_max_target_accumulated = 0
throttle_value_accumulated = 0
def motor_control():
    ##########################################################################################
    # Throttle
    # map torque value
    if motor_control_scheme == 'current':
        motor_max_target = motor_max_current_limit
    elif motor_control_scheme == 'speed':
        # low pass filter battery voltage
        erpm_target = ebike.battery_voltage * 294 # this motor has near 11.9k erpm on max battery voltage 40.5V
        global motor_max_target_accumulated
        motor_max_target_accumulated -= ((int(motor_max_target_accumulated)) >> 7)
        motor_max_target_accumulated += erpm_target
        motor_max_target = (int(motor_max_target_accumulated)) >> 7
      
    motor_target = simpleio.map_range(
        ebike.throttle_value,
        throttle_min, # min input
        throttle_max, # max input
        0, # min output
        motor_max_target) # max output
    ##########################################################################################

    # impose a min motor target value, as to much lower value will make the motor vibrate and not run (??)
    if motor_control_scheme == 'current':
        if motor_target < motor_min_current_start:
            motor_target = 0
    elif motor_control_scheme == 'speed':
        if motor_target < 1260: # about 3.5 km/h
            motor_target = 0
  
    # apply ramp up / down factor: faster when ramp down
    if motor_target > ebike.motor_target:
        ramp_time = ramp_up_time
    else:
        ramp_time = ramp_down_time
        
    time_now = time.monotonic_ns()
    ramp_step = (time_now - ebike.ramp_last_time) / (ramp_time * 1000000000)
    ebike.ramp_last_time = time_now
    ebike.motor_target = utils_step_towards(ebike.motor_target, motor_target, ramp_step)

    # let's limit the value
    if motor_control_scheme == 'current':
        if ebike.motor_target > motor_max_current_limit:
            ebike.motor_target = motor_max_current_limit
    # no limit for speed mode

    # limit very small and negative values
    if ebike.motor_target < 0.001:
        ebike.motor_target = 0

    # check if brakes are active
    if ebike.brakes_value > 47:
        ebike.brakes_are_active = True
    else:
        ebike.brakes_are_active = False

    # let's update the motor current, only if the target value changed and brakes are not active
    if ebike.brakes_are_active:
        if motor_control_scheme == 'current':
            vesc.set_motor_current_amps(0)
        elif motor_control_scheme == 'speed':
            vesc.set_motor_speed_erpm(0)

        ebike.motor_target = 0
        ebike.previous_motor_target = 0
      
    elif ebike.motor_target != ebike.previous_motor_target:
        ebike.previous_motor_target = ebike.motor_target

        if motor_control_scheme == 'current':
            vesc.set_motor_current_amps(ebike.motor_target)
        elif motor_control_scheme == 'speed':
            # when speed is near zero, set motor current to 0 to release the motor
            if ebike.motor_target == 0 and ebike.motor_speed_erpm < 750: # about 2 km/h:
                vesc.set_motor_current_amps(0)
            else:
                vesc.set_motor_speed_erpm(ebike.motor_target)
    
    # for debug only        
    # print()
    # print(ebike.brakes_value, ebike.throttle_value, int(ramp_step), int(motor_target), int(ebike.motor_target))

async def task_read_sensors_control_motor():
    while True:
        # motor control
        motor_control()

        # idle 20ms
        await asyncio.sleep(0.02)

async def task_various_0_5s():
    assert(wheel_circunference > 100), "wheel_circunference must be higher then 100mm (4 inches wheel)"
    
    while True:
        # calculate wheel speed
        # 15 pole pairs on Xiaomi M365 motor
        # 1h --> 60 minutes
        # 60 * 3.14 = 188.4
        # 188.4 / 15 = 12,56
        # mm to km --> 1000000 --> 0,00001256
        ebike.wheel_speed = int(wheel_circunference * ebike.motor_speed_erpm * 0.00001256)
        if ebike.wheel_speed > 99:
            ebike.wheel_speed = 99
        elif ebike.wheel_speed < 0:
            ebike.wheel_speed = 0

        # let's signal to update data to dashboard
        ebike.update_data_to_dashboard = True

        await asyncio.sleep(0.5)

async def main():

    print("starting")

    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    dashboard_task = asyncio.create_task(task_dashboard())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())
    various_0_5s_task = asyncio.create_task(task_various_0_5s())

    await asyncio.gather(vesc_heartbeat_task,
                         dashboard_task,
                         read_sensors_control_motor_task,
                         various_0_5s_task)

asyncio.run(main())
