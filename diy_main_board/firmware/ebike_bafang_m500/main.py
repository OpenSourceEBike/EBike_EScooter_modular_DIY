import board
import time
import supervisor
import simpleio
import asyncio
import Brake
import ebike_bafang_m500.torque_sensor as torque_sensor
import ebike_bafang_m500.display_espnow as DisplayESPnow
from microcontroller import watchdog
from watchdog import WatchDogMode
import wifi
import gc
from vars import Vars, Cfg, MotorCfg
from motor import MotorData, Motor

# Tested on a ESP32-S3-DevKitC-1-N8R2

supervisor.runtime.autoreload = False

print()
print("Booting EBike/EScooter software")

# This board MAC Address
cfg = Cfg()
cfg.my_mac_address =      [0x68, 0xb6, 0xb3, 0x01, 0xa7, 0xb2]

# MAC Address value needed for the wireless communication with the display
cfg.display_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xa7, 0xb3]

# setup radio MAC Adreess
wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(cfg.my_mac_address)

# object that holds various variables
vars = Vars()

###############################################
# OPTIONS

torque_sensor_weight_min_to_start_x10 = 40 # (value in kgs) let's avoid any false startup, we will need this minimum weight on the pedals to start
torque_sensor_weight_max_x10 = 400 # torque sensor max value is 40 kgs. Let's use the max range up to 40 kgs

motor_min_current_start = 1.5 # to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
motor_max_current_limit = 15.0 # max value, be carefull to not burn your motor

ramp_up_time = 0.1 # ram up time for each 1A
ramp_down_time = 0.05 # ram down time for each 1A

###############################################

assist_level_factor_table = [
    0,
    0.13,
    0.16,
    0.20,
    0.24,
    0.31,
    0.38,
    0.48,
    0.60,
    0.75,
    0.93,
    1.16,
    1.46,
    1.82,
    2.27,
    2.84,
    3.55,
    4.44,
    5.55,
    6.94,
    8.67
]

brake = Brake.Brake(board.IO10) # brake sensor pin

torque_sensor = torque_sensor.TorqueSensor(
    board.IO4, # CAN tx pin
    board.IO5) # CAN rx pin

# rear motor VESC is connected by UART
motor_cfg = MotorCfg(0)
motor_cfg.uart_tx_pin = board.IO13 # UART TX pin that connect to VESC
motor_cfg.uart_rx_pin = board.IO14 # UART RX pin that connect to VESC
motor_cfg.uart_baudrate = 115200 # VESC UART baudrate
motor_data = MotorData(motor_cfg)

motor_dummy_cfg = MotorCfg(1)
motor_dummy_data = MotorData(motor_dummy_cfg)
motor_dummy = Motor(motor_dummy_data)

motor = Motor(motor_data)

# object to communicate with the display wireless by ESPNow
display = DisplayESPnow.Display(vars, motor.data, cfg.display_mac_address)

def check_brakes():
    """Check the brakes and if they are active, set the motor current to 0
    """
    global vars
    global brake
    global motor
    global motor_current_target
    
    if vars.brakes_are_active == False and brake.value == True:
        # brake / coast the motor
        motor.set_motor_current_amps(0)
        motor_current_target = 0
        vars.brakes_are_active = True
      
    elif vars.brakes_are_active == True and brake.value == False:
        vars.brakes_are_active = False
  
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


async def task_display_send_data():
    global display
    
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()
        
        # send data to the display
        display.send_data()

        gc.collect()
        await asyncio.sleep(0.15)


async def task_display_receive_process_data():
    global display
    
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()
        
        # received and process data from the display
        display.receive_process_data()

        gc.collect()
        await asyncio.sleep(0.15)
        
        
async def task_motors_refresh_data():
    global motor
    
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()
        
        # refresh latest for VESC data
        motor.update_motor_data()

        gc.collect()
        await asyncio.sleep(0.1)

motor_current_target_previous = 0
ramp_last_time = time.monotonic_ns()
def motor_control():
    global vars
    global motor_max_current_limit
    global torque_sensor_weight_min_to_start_x10
    global torque_sensor_weight_max_x10
    global assist_level_factor_table
    global assist_level
    global ramp_last_time
    global motor_current_target_previous
    
    check_brakes()
    
    ##########################################################################################
    # Torque sensor input to motor_current_target
    
    motor_current_target = 0

    # read the values from torque sensor
    torque_weight_x10, cadence = torque_sensor.value
    if torque_weight_x10 is not None:
        
        # map torque value to motor current
        motor_current_target = simpleio.map_range(
            torque_weight_x10,
            torque_sensor_weight_min_to_start_x10, # min input
            torque_sensor_weight_max_x10, # max input
            0, # min output
            motor_max_current_limit) # max output

        # apply the assist level
        assist_level_factor = assist_level_factor_table[vars.assist_level]
        motor_current_target = motor_current_target * assist_level_factor
    ##########################################################################################

    # impose a min motor current value, as to much lower value will make the motor vibrate and not run (??)
    if motor_current_target < motor_min_current_start:
        motor_current_target = 0

    # apply ramp up / down factor: faster when ramp down
    if motor_current_target > motor_current_target_previous:
        ramp_time = ramp_up_time
    else:
        ramp_time = ramp_down_time
        
    time_now = time.monotonic_ns()
    ramp_step = (time_now - ramp_last_time) / (ramp_time * 1000000000)
    ramp_last_time = time_now
    motor_current_target = utils_step_towards(motor_current_target_previous, motor_current_target, ramp_step)

    # let's limit the value
    if motor_current_target > motor_max_current_limit:
        motor_current_target = motor_max_current_limit

    if motor_current_target < 0.0:
        motor_current_target = 0

    # Should we disable the motor?
    if vars.brakes_are_active == True or \
            vars.motors_enable_state == False:
        motor_current_target = 0

    # let's update the motor current
    motor.set_motor_current_amps(motor_current_target)
    
    # keep track of motor_current_target
    motor_current_target_previous = motor_current_target
    
    # We just updated the motor target, so let's feed the watchdog to avoid a system reset
    watchdog.feed() # avoid system reset because watchdog timeout


async def task_read_sensors_control_motor():
    
    while True:
        # are breaks active and we should disable the motor?
        check_brakes()

        # motor control
        motor_control()

        # idle 20ms
        gc.collect()
        await asyncio.sleep(0.02)

async def main():

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    watchdog.timeout = 1
    watchdog.mode = WatchDogMode.RESET

    motors_refresh_data_task = asyncio.create_task(task_motors_refresh_data())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())
    display_send_data_task = asyncio.create_task(task_display_send_data())
    display_receive_process_data_task = asyncio.create_task(task_display_receive_process_data())

    print("Starting EBike/EScooter")
    print()

    await asyncio.gather(
        motors_refresh_data_task,
        read_sensors_control_motor_task,
        display_send_data_task,
        display_receive_process_data_task)

asyncio.run(main())
