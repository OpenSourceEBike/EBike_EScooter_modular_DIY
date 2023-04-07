import board
import time
import supervisor
import array
import simpleio
import asyncio
import ebike_data
import vesc
import busio
import m365_dashboard
import simpleio

import supervisor
supervisor.runtime.autoreload = False

# Tested on a ESP32-S3-DevKitC-1-N8R2

###############################################
# OPTIONS

throttle_max = 175
throttle_min = 45

motor_min_current_start = 0.0 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 30.0 # max value, be carefull to not burn your motor

ramp_up_time = 0.005 # ram up time for each 1A
ramp_down_time = 0.005 # ram down time for each 1A

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
# vesc.set_motor_current_brake_amps(0)

dashboard = m365_dashboard.M365_dashboard(
    board.IO12, # UART TX pin
    board.IO11, # UART RX pin
    ebike)

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

motor_current_target__torque_sensor = 0
def motor_control():
    ##########################################################################################
    # Throttle
    # map torque value to motor current
    motor_current_target = simpleio.map_range(
        ebike.throttle_value,
        throttle_min, # min input
        throttle_max, # max input
        0, # min output
        motor_max_current_limit) # max output
    ##########################################################################################

    # impose a min motor current value, as to much lower value will make the motor vibrate and not run (??)
    if motor_current_target < motor_min_current_start:
        motor_current_target = 0

    # apply ramp up / down factor: faster when ramp down
    if motor_current_target > ebike.motor_current_target:
        ramp_time = ramp_up_time
    else:
        ramp_time = ramp_down_time
        
    time_now = time.monotonic_ns()
    ramp_step = (time_now - ebike.ramp_last_time) / (ramp_time * 1000000000)
    ebike.ramp_last_time = time_now
    ebike.motor_current_target = utils_step_towards(ebike.motor_current_target, motor_current_target, ramp_step)

    # let's limit the value
    if ebike.motor_current_target > motor_max_current_limit:
        ebike.motor_current_target = motor_max_current_limit

    if ebike.motor_current_target < 0.0:
        ebike.motor_current_target = 0

    # if brakes are active, reset motor_current_target
    if ebike.brakes_value > 50:
        ebike.brakes_are_active = True
    else:
        ebike.brakes_are_active = False

    if ebike.brakes_are_active == True:
        ebike.motor_current_target = 0

    # let's update the motor current, only if the target value changed
    if ebike.motor_current_target != ebike.previous_motor_current_target:
        ebike.previous_motor_current_target = ebike.motor_current_target
        # vesc.set_motor_current_amps(ebike.motor_current_target)
        vesc.set_motor_speed_erpm(800 + (ebike.motor_current_target * 333))
    
    print(f'{ebike.motor_current_target * 333}')

async def task_read_sensors_control_motor():
    while True:
        # motor control
        motor_control()

        # idle 20ms
        await asyncio.sleep(0.02)

async def main():

    print("starting")

    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    dashboard_task = asyncio.create_task(task_dashboard())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())

    await asyncio.gather(vesc_heartbeat_task, dashboard_task, read_sensors_control_motor_task)

asyncio.run(main())

