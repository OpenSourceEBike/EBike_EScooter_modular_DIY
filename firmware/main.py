import board
import time
import simpleio
import asyncio
import ebike_app_data
import throttle
import brake_sensor
import wheel_speed_sensor
import torque_sensor
import vesc
import display

# Tested on a ESP32-S3-DevKitC-1-N8R2

brake_sensor = brake_sensor.BrakeSensor(
   board.IO10) #brake sensor pin

# wheel_speed_sensor = wheel_speed_sensor.WheelSpeedSensor(
#    board.IO46) #wheel speed sensor pin

torque_sensor = torque_sensor.TorqueSensor(
    board.IO4, #SPI CS pin
    board.IO5, #SPI clock pin
    board.IO6, #SPI MOSI pin
    board.IO7) #SPI MISO pin

# throttle = throttle.Throttle(
#     board.IO9, # ADC pin for throttle
#     min = 17000, # min ADC value that throttle reads, plus some margin
#     max = 50000) # max ADC value that throttle reads, minus some margin

ebike_data = ebike_app_data.EBikeAppData()
vesc = vesc.Vesc(
    board.IO14, #UART TX pin that connect to VESC
    board.IO13, #UART RX pin that connect to VESC
    ebike_data) #VESC data object to hold the VESC data

display = display.Display(
    board.IO12, #UART TX pin that connect to display
    board.IO11, #UART RX pin that connect to display
    ebike_data)

def check_brakes():
    """Check the brakes and if they are active, set the motor current to 0
    """
    if brake_sensor.value == True:
        vesc.set_current_amps(0) # set the motor current to 0 will efectivly stop the motor
        ebike_data.brakes_are_active = True
    else:
        ebike_data.brakes_are_active = False

def print_ebike_data_to_terminal():
    """Print EBike data to terminal
    """
    print(" ")
    print(f"tor {ebike_data.torque_weight}")
    print(f"cad {ebike_data.cadence}")
    
    if brake_sensor.value:
        print("brk 1")
    else:
        print("brk 0")

    print(f"mot curr {ebike_data.battery_current:.1f}")

def utils_step_towards(current_value, goal, step):
    value = current_value

    if current_value < goal:
        if (current_value + step) < goal:
            value += step
        else:
            value = goal
    
    elif current_value > goal:
        if (current_value - step) > goal:
            value -= step
        else:
            value = goal

    return value

async def task_display_process():
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()

        # need to process display data periodically
        display.process_data()

        # idle 20ms, fine tunned
        await asyncio.sleep(0.02)

async def task_vesc_heartbeat():
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()
        
        # VESC heart beat must be sent more frequently than 1 second, otherwise the motor will stop
        vesc.send_heart_beat()
        
        # ask for VESC latest data
        vesc.refresh_data()
        
        print_ebike_data_to_terminal()
        
        await asyncio.sleep(0.5) # idle 500ms

async def task_read_sensors_control_motor():
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()

        # read torque sensor data and map to motor current
        torque_weight, cadence = torque_sensor.weight_value
        if torque_weight is not None:
            # let's save this values
            ebike_data.torque_weight = torque_weight
            ebike_data.cadence = cadence

            # map torque value to motor current
            motor_current = simpleio.map_range(
                torque_weight,
                1.0, #min
                10.0, #max
                0, #min current
                10.0) #max current

            if motor_current < 5.0:
                motor_current = 0

            # apply ramp up / down
            if motor_current > ebike_data.motor_current_target:
                ramp_time = 0.01
            else:
                ramp_time = 0.01
              
            time_now = time.monotonic_ns()
            ramp_step = (time.monotonic_ns() - ebike_data.ramp_up_last_time) / (ramp_time * 1_000_000_000)
            ebike_data.ramp_up_last_time = time_now
            ebike_data.motor_current_target = utils_step_towards(ebike_data.motor_current_target, motor_current, ramp_step)
       
            # let's update the motor current, only if the target value changed and brakes are not active
            if motor_current != ebike_data.previous_motor_current and ebike_data.brakes_are_active == False:
                 ebike_data.previous_motor_current = ebike_data.motor_current_target
                 vesc.set_current_amps(ebike_data.motor_current_target)

        # idle 20ms
        await asyncio.sleep(0.02)

async def main():
  
    print("starting")
    time.sleep(2) # boot init delay time so the display will be ready

    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())
    display_process_task = asyncio.create_task(task_display_process())
    await asyncio.gather(
        vesc_heartbeat_task,
        read_sensors_control_motor_task,
        display_process_task)
    print("done main()")

asyncio.run(main())
