import board
import time
import supervisor
import simpleio
import asyncio
import ebike_data
import throttle
import brake_sensor
import wheel_speed_sensor
import torque_sensor
import vesc
import display

# Tested on a ESP32-S3-DevKitC-1-N8R2

###############################################
# OPTIONS

# Increase or decrease this value to have higher or lower motor assistance
# Default value: 1.0
assist_level_factor = 3.0

torque_sensor_weight_min_to_start = 4.0 # (value in kgs) let's avoid any false startup, we will need this minimum weight on the pedals to start
torque_sensor_weight_max = 40.0 # torque sensor max value is 40 kgs. Let's use the max range up to 40 kgs

motor_min_current_start = 1.5 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 15.0 # max value, be carefull to not burn your motor

ramp_up_time = 0.1 # ram up time for each 1A
ramp_down_time = 0.05 # ram down time for each 1A

# debug options
enable_print_ebike_data_to_terminal = True
enable_debug_log_cvs = False

###############################################

# open file for log data
log = open("/log_csv.txt", "w")

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

ebike = ebike_data.EBike()
vesc = vesc.Vesc(
    board.IO14, #UART TX pin tebike_app_datahat connect to VESC
    board.IO13, #UART RX pin that connect to VESC
    ebike) #VESC data object to hold the VESC data

display = display.Display(
    board.IO12, #UART TX pin that connect to display
    board.IO11, #UART RX pin that connect to display
    ebike)

def check_brakes():
    """Check the brakes and if they are active, set the motor current to 0
    """
    if ebike.brakes_are_active == False and brake_sensor.value == True:
        vesc.set_motor_current_amps(0) # set the motor current to 0 will efectively coast the motor
        ebike.motor_current_target = 0
        ebike.brakes_are_active = True

        ebike.brakes_counter += 1
      
    elif ebike.brakes_are_active == True and brake_sensor.value == False:
        ebike.brakes_are_active = False

def print_ebike_data_to_terminal():
    """Print EBike data to terminal
    """
    if ebike.battery_current < 0:
       ebike.battery_current = 0

    if ebike.motor_current < 0:
       ebike.motor_current = 0
  
    print(f" {ebike.brakes_counter:3} | {ebike.motor_current_target:2.1f} | {ebike.motor_current:2.1f} | {ebike.battery_current:2.1f}", end='\r')
    # print(f" {ebike.torque_weight: 2.1f} | {ebike.cadence: 3}", end='\r')
    
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

async def task_log_data():
    while True:
        # log data to local file system CSV file
        brake = 0
        if brake_sensor.value:
            brake = 1
        log.write(f"{ebike.torque_weight:.1f},{ebike.cadence},{brake},{ebike.battery_current:.1f},{ebike.motor_current:.1f}\n")
        print(supervisor.ticks_ms())

        ebike.log_flush_cnt += 1
        if ebike.log_flush_cnt > 200:
            ebike.log_flush_cnt = 0
            log.flush()

        # idle 25ms, fine tunned
        await asyncio.sleep(0.025)

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

        # should we print EBike data to terminal?
        if enable_print_ebike_data_to_terminal == True:
            print_ebike_data_to_terminal()

        # idle 500ms
        await asyncio.sleep(0.5) 

async def task_read_sensors_control_motor():
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()

        # read torque sensor data and map to motor current
        torque_weight, cadence = torque_sensor.weight_value_cadence_filtered
        # store cadence
        ebike.cadence = cadence

        if torque_weight is not None:
            # store torque
            ebike.torque_weight = torque_weight

            # map torque value to motor current
            motor_current_target = simpleio.map_range(
                torque_weight,
                torque_sensor_weight_min_to_start, # min input
                torque_sensor_weight_max, # max input
                0, # min output
                motor_max_current_limit) # max output

            # apply the assist level
            motor_current_target *= (assist_level_factor * \
                    2.0)  # to keep assist_level_factor default value as 1.0, let's multiply by 2 as the default value should be in reality 2.0 for my taste

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

            # let's make sure it is not over the limit
            if ebike.motor_current_target > motor_max_current_limit:
                ebike.motor_current_target = motor_max_current_limit

            # if brakes are active, reset motor_current_target
            if ebike.brakes_are_active == True:
               ebike.motor_current_target = 0
               ebike.previous_motor_current_target = 0
       
            # let's update the motor current, only if the target value changed and brakes are not active
            if ebike.motor_current_target != ebike.previous_motor_current_target and \
                    ebike.brakes_are_active == False:
                ebike.previous_motor_current_target = ebike.motor_current_target
                vesc.set_motor_current_amps(ebike.motor_current_target)

        # idle 20ms
        await asyncio.sleep(0.02)

async def main():

    print("starting")
    time.sleep(2) # boot init delay time so the display will be ready

    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())
    display_process_task = asyncio.create_task(task_display_process())

    # Start the tasks. Note that log_data_task may be disabled as a configuration
    if enable_debug_log_cvs == False:
        await asyncio.gather(
            vesc_heartbeat_task,
            read_sensors_control_motor_task,
            display_process_task)
    else:
        log_data_task = asyncio.create_task(task_log_data())
        await asyncio.gather(
            vesc_heartbeat_task,
            read_sensors_control_motor_task,
            display_process_task,
            log_data_task)
  
    print("done main()")

asyncio.run(main())