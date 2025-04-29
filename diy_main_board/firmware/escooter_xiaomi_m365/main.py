# #The following code is useful for development
# import supervisor
# if supervisor.runtime.run_reason != supervisor.RunReason.REPL_RELOAD:
#     # If not a soft reload, exit immediately
#     print("Code not run at startup. Press Ctrl+D to run.")
#     while True:
#          pass # Or use time.sleep(1000) to keep the device from doing anything.
# else:
#     # Your code that should run only on Ctrl+D goes here
#     print("Running on Ctrl+D (soft reload).")
#     # ... your main code ...


# Tested on a ESP32-S3-DevKitC-1-N8R2

import board
import time
import supervisor
import simpleio
import asyncio
import brake_analog
import throttle as Throttle
import escooter_xiaomi_m365.display_espnow as DisplayESPnow
from microcontroller import watchdog
from watchdog import WatchDogMode
import wifi
import gc
from vars import Vars
from motor import MotorData, Motor
from configurations_escooter_xiaomi_m365 import cfg, front_motor_cfg

supervisor.runtime.autoreload = False

print()
print("Booting EBike/EScooter software")

# setup radio MAC Adreess
wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(cfg.my_mac_address)

# object that holds various variables
vars = Vars()

# object for the handle bar throttle
throttle = Throttle.Throttle(
    cfg.throttle_1_pin,
    min = cfg.throttle_1_adc_min, # min ADC value that throttle reads, plus some margin
    max = cfg.throttle_1_adc_max) # max ADC value that throttle reads, minus some margin

# object to read the analog brake
brake = brake_analog.BrakeAnalog(
    cfg.brake_pin,
    cfg.brake_analog_adc_min,
    cfg.brake_analog_adc_max)

# if brakes are active at startup, block here
# this is needed for development, to help keep the motor disabled
while brake.value > cfg.brake_analog_adc_min:
    print('brake at start')
    time.sleep(1)

# Objects to control the motors
# Delay time needed for the CAN initialization (??), otherwise CAN will not work
time.sleep(2.5)
front_motor_data = MotorData(front_motor_cfg)
front_motor = Motor(front_motor_data)

# object to communicate with the display wireless by ESPNow
display = DisplayESPnow.Display(vars, front_motor.data, cfg.display_mac_address)


async def task_motor_refresh_data():
    global front_motor
    
    while True:
        # Refresh latest for VESC data
        front_motor.update_motor_data(front_motor)
        
        gc.collect()
        await asyncio.sleep(0.05)


async def task_display_send_data():
    global display
    
    while True:
        # send data to the display
        # Avoid send data while display is not ready
        if vars.motors_enable_state == True:
            display.send_data()

        gc.collect()
        await asyncio.sleep(0.15)


async def task_display_receive_process_data():
    global display
    
    while True:
        # Received and process data from the displaye:
        display.receive_process_data()

        gc.collect()
        await asyncio.sleep(0.1)
        

async def task_control_motor():
    global vars
    global cfg
    global button_press_state_previous
    global front_motor
    global throttle
    global brake
    
    while True:
        ##########################################################################################
        # Throttle
        
        # Read throttle
        throttle_adc_value = throttle.adc_value
        throttle_value = throttle.value

        # Check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        if throttle_adc_value > cfg.throttle_1_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            # VESC set_motor_current_amps command will release the motor
            front_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)

            message = f'throttle value: {throttle_value} -- is over max, this can be dangerous!'    
            raise Exception(message)
        
        # Read brake
        brake_adc_value = brake.adc_value
        brake_value = brake.value
        
        # Check to see if brake analog is over the suposed max error value
        if brake_adc_value > cfg.brake_analog_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            # VESC set_motor_current_amps command will release the motor
            front_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)

            message = f'brake value: {brake_value} -- is over max!'    
            raise Exception(message)
            
        # Calculate target speed
        motor_target_speed = simpleio.map_range(
            throttle_value,
            0.0,
            1000.0,
            0.0,
            front_motor.data.cfg.motor_erpm_max_speed_limit)
        
        motor_target_regen_current = simpleio.map_range(
            brake_value,
            0.0,
            1000.0,
            0.0,
            front_motor_cfg.motor_max_current_limit_min)
        
        # Limit mins and max values
        if motor_target_speed < 500.0:
            motor_target_speed = 0.0
        
        if motor_target_speed > \
            front_motor.data.cfg.motor_erpm_max_speed_limit:
            motor_target_speed = front_motor.data.cfg.motor_erpm_max_speed_limit
        
        # Check if brakes are active
        vars.brakes_are_active = True if brake_value > 0 else False

        # Keep motor regen current at max if not brakes are active
        if vars.brakes_are_active == False:
            motor_target_regen_current = front_motor_cfg.motor_max_current_limit_min
            
        # Set max motor currents: max current and max regen/brake current
        front_motor.set_motor_current_limits(
            motor_target_regen_current,
            front_motor_cfg.motor_max_current_limit_max)

        # If motor state is disabled, set motor current to 0 to release the motor
        if vars.motors_enable_state == False:
            front_motor.set_motor_current_amps(0)
            
        else:
            # If brakes are active, set motor speed to 0 to try stop/brake/regen
            if vars.brakes_are_active:
                front_motor.set_motor_speed_rpm(0)

            # If brakes are not active, set the motor speed
            else:
                front_motor.set_motor_speed_rpm(motor_target_speed)

                        
        # print('brake_value', brake_value)
        # print('throttle_value', throttle_value)
        # print('brakes', vars.brakes_are_active)
        # print('currents', motor_target_regen_current, front_motor_cfg.motor_max_current_limit_max)
        # print('target_speed', motor_target_speed)
        # print()

        
        # We just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.02)

wheel_speed_previous_motor_speed_erpm = 0
async def task_various():
    global front_motor
    global wheel_speed_previous_motor_speed_erpm
    
    while True:

        # calculate the rear motor wheel speed
        if front_motor.data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = front_motor.data.speed_erpm
        
            # Calculate the wheel speed in km/h
            perimeter = 6.28 * front_motor.data.cfg.wheel_radius # 2*pi = 6.28
            motor_rpm = front_motor.data.speed_erpm / front_motor.data.cfg.poles_pair
            front_motor.data.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60.0)

            if abs(front_motor.data.wheel_speed < 2.0):
                front_motor.data.wheel_speed = 0.0

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.1)
        
async def main():

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    watchdog.timeout = 1
    watchdog.mode = WatchDogMode.RESET

    motor_refresh_data_task = asyncio.create_task(task_motor_refresh_data())
    control_motor_task = asyncio.create_task(task_control_motor())
    display_send_data_task = asyncio.create_task(task_display_send_data())
    display_receive_process_data_task = asyncio.create_task(task_display_receive_process_data())
    various_task = asyncio.create_task(task_various())

    print("Starting EBike/EScooter")
    print()

    await asyncio.gather(motor_refresh_data_task,
                        display_send_data_task,
                        display_receive_process_data_task,
                        control_motor_task,
                        various_task)

asyncio.run(main())

