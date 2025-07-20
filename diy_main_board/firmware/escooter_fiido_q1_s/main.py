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

import time
import supervisor
import asyncio
import simpleio
import Brake
import throttle as Throttle
from microcontroller import watchdog
from watchdog import WatchDogMode
import gc
import escooter_fiido_q1_s.display_espnow as DisplayESPnow
import wifi
from vars import Vars
from motor import MotorData, Motor
from configurations_escooter_fiido_q1_s import cfg, front_motor_cfg, rear_motor_cfg

supervisor.runtime.autoreload = False

print()
print("Booting EBike/EScooter software")

# setup radio MAC Adreess
wifi.radio.enabled = True
wifi.radio.mac_address = bytearray(cfg.my_mac_address)

# object that holds various variables
vars = Vars()

# object to read the brake state
brake_sensor = Brake.Brake(cfg.brake_pin)

# if brakes are active at startup, block here
# this is needed for development, to help keep the motor and the UART disable
while brake_sensor.value:
    print('brake at start')
    time.sleep(1)

# objects to control the motors
front_motor_data = MotorData(front_motor_cfg)
rear_motor_data = MotorData(rear_motor_cfg)
front_motor = Motor(front_motor_data)
rear_motor = Motor(rear_motor_data)

# initialize the variables with the configuration values
front_motor.data.motor_target_current_limit_max = front_motor.data.cfg.motor_max_current_limit_max
front_motor.data.motor_target_current_limit_min = front_motor.data.cfg.motor_max_current_limit_min
front_motor.data.battery_target_current_limit_max = front_motor.data.cfg.battery_max_current_limit_max
front_motor.data.battery_target_current_limit_min = front_motor.data.cfg.battery_max_current_limit_min
rear_motor.data.motor_target_current_limit_max = rear_motor.data.cfg.motor_max_current_limit_max
rear_motor.data.motor_target_current_limit_min = rear_motor.data.cfg.motor_max_current_limit_min
rear_motor.data.battery_target_current_limit_max = rear_motor.data.cfg.battery_max_current_limit_max
rear_motor.data.battery_target_current_limit_min = rear_motor.data.cfg.battery_max_current_limit_min

# object to communicate with the display wireless by ESPNow
display = DisplayESPnow.Display(vars, front_motor.data, rear_motor.data, cfg.display_mac_address)

# object for left handle bar throttle
throttle_1 = Throttle.Throttle(
    cfg.throttle_1_pin,
    min = cfg.throttle_1_adc_min, # min ADC value that throttle reads, plus some margin
    max = cfg.throttle_1_adc_max) # max ADC value that throttle reads, minus some margin

# object for right handle bar throttle
throttle_2 = Throttle.Throttle(
    cfg.throttle_2_pin,
    min = cfg.throttle_2_adc_min, # min ADC value that throttle reads, plus some margin
    max = cfg.throttle_2_adc_max) # max ADC value that throttle reads, minus some margin

async def task_motors_refresh_data():
    global front_motor
    global rear_motor
    
    while True:
        # Refresh latest for VESC data
        # Only do call this for one motor!!
        rear_motor.update_motor_data(rear_motor, front_motor)
        await asyncio.sleep(0.05)

async def task_display_send_data():
    global display
    
    while True:
        # send data to the display
        display.send_data()

        gc.collect()
        await asyncio.sleep(0.15)


async def task_display_receive_process_data():
    global display
    
    while True:
        # received and process data from the display
        display.receive_process_data()

        gc.collect()
        await asyncio.sleep(0.1)
        

def cruise_control(vars, wheel_speed, throttle_value):
    button_long_press_state = vars.buttons_state & 0x0200
    
    # Set initial variables values
    if vars.cruise_control.state == 0:     
        vars.cruise_control.button_long_press_previous_state = button_long_press_state
        vars.cruise_control.state = 1
    
    # Wait for conditions to start cruise control
    if vars.cruise_control.state == 1:        
        if (button_long_press_state != vars.cruise_control.button_long_press_previous_state) and wheel_speed > 4.0:
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            
            vars.cruise_control.throttle_value = throttle_value
            vars.cruise_control.state = 2
            
    # Cruise control is active
    if vars.cruise_control.state == 2:
        # Check for button pressed
        vars.cruise_control.button_pressed = False
        button_press_state = vars.buttons_state & 0x0100
        if button_press_state != vars.cruise_control.button_press_previous_state:
            vars.cruise_control.button_press_previous_state = button_press_state
            vars.cruise_control.button_pressed = True
        
        # Check for conditions to stop cruise control
        if vars.brakes_are_active or vars.cruise_control.button_pressed or throttle_value > (vars.cruise_control.throttle_value * 1.15):
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            vars.cruise_control.state = 1
        else:
            # Keep cruising...
            # overide the throttle value
            throttle_value = vars.cruise_control.throttle_value
        
    return throttle_value

async def task_control_motor():
    global vars
    global cfg
    global button_press_state_previous
    global front_motor
    global rear_motor
    global throttle_1
    global throttle_2
    global brake_sensor
    
    while True:
        ##########################################################################################
        # Throttle
        
        # read 1st and 2nd throttle, and use the max value of both
        throttle_1_value = throttle_1.value
        throttle_2_value = throttle_2.value                    
        throttle_value = max(throttle_1_value, throttle_2_value)
        
        # check to see if throttle is over the suposed max error value,
        # if this happens, that probably means there is an issue with ADC and this can be dangerous,
        # as this did happen a few times during development and motor keeps running at max target / current / speed!!
        # the raise Exception() will reset the system
        if throttle_1_value > cfg.throttle_1_adc_over_max_error or \
                throttle_2_value > cfg.throttle_2_adc_over_max_error:
            # send 3x times the motor current 0, to make sure VESC receives it
            # VESC set_motor_current_amps command will release the motor
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
                
            if throttle_1_value > cfg.throttle_1_adc_over_max_error:
                message = f'throttle 1 value: {throttle_1_value} -- is over max, this can be dangerous!'
            else:
                message = f'throttle 2 value: {throttle_2_value} -- is over max, this can be dangerous!'
            raise Exception(message)
            pass
    
        # Apply cruise control
        throttle_value = cruise_control(
            vars,
            rear_motor.data.wheel_speed,
            throttle_value)
        
        # Calculate target speed
        front_motor.data.motor_target_speed = simpleio.map_range(
            throttle_value,
            0.0,
            1000.0,
            0.0,
            front_motor.data.cfg.motor_erpm_max_speed_limit)
        
        rear_motor.data.motor_target_speed = simpleio.map_range(
            throttle_value,
            0.0,
            1000.0,
            0.0,
            rear_motor.data.cfg.motor_erpm_max_speed_limit)

        # Limit mins and max values
        if front_motor.data.motor_target_speed < 500.0:
            front_motor.data.motor_target_speed = 0.0
        if rear_motor.data.motor_target_speed < 500.0:
            rear_motor.data.motor_target_speed = 0.0
        
        if front_motor.data.motor_target_speed > \
            front_motor.data.cfg.motor_erpm_max_speed_limit:
            front_motor.data.motor_target_speed = front_motor.data.cfg.motor_erpm_max_speed_limit
        
        if rear_motor.data.motor_target_speed > \
            rear_motor.data.cfg.motor_erpm_max_speed_limit:
            rear_motor.data.motor_target_speed = rear_motor.data.cfg.motor_erpm_max_speed_limit

        # Set motor min and max currents        
        front_motor.set_motor_current_limits(
            front_motor.data.motor_target_current_limit_min,
            front_motor.data.motor_target_current_limit_max)
        
        rear_motor.set_motor_current_limits(
            rear_motor.data.motor_target_current_limit_min,
            rear_motor.data.motor_target_current_limit_max)

        # Set battery min and max currents        
        front_motor.set_battery_current_limits(
            front_motor.data.battery_target_current_limit_min,
            front_motor.data.battery_target_current_limit_max)
        
        rear_motor.set_battery_current_limits(
            rear_motor.data.battery_target_current_limit_min,
            rear_motor.data.battery_target_current_limit_max)
        
        # Check if brakes are active
        vars.brakes_are_active = True if brake_sensor.value else False

        # If motor state is disabled, set motor current to 0 to release the motor
        if vars.motors_enable_state == False:
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
        else:
            # If brakes are active, set motor speed to 0 to have the highest brake / regen
            if vars.brakes_are_active:
                front_motor.set_motor_speed_rpm(0)
                rear_motor.set_motor_speed_rpm(0)

            # If brakes are not active, set the motor speed
            else:
                front_motor.set_motor_speed_rpm(front_motor.data.motor_target_speed)
                rear_motor.set_motor_speed_rpm(rear_motor.data.motor_target_speed)
            
        # We just updated the motor target, so let's feed the watchdog to avoid a system reset
        watchdog.feed() # avoid system reset because watchdog timeout

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.02)
        
async def task_control_motor_limit_current():
    global front_motor
    global rear_motor
    
    while True:
        ##########################################################################################
        # always considers the rear motor wheel speed, as the front motor wheel can make a skid
        front_motor.data.motor_target_current_limit_max = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            front_motor.data.cfg.motor_current_limit_max_min_speed,
            front_motor.data.cfg.motor_current_limit_max_max,
            front_motor.data.cfg.motor_current_limit_max_min)
        
        rear_motor.data.motor_target_current_limit_max = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_max_min_speed,
            rear_motor.data.cfg.motor_current_limit_max_max,
            rear_motor.data.cfg.motor_current_limit_max_min)
        
        
        front_motor.data.motor_target_current_limit_min = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            front_motor.data.cfg.motor_current_limit_min_max_speed,
            front_motor.data.cfg.motor_current_limit_min_max,
            front_motor.data.cfg.motor_current_limit_min_min)
        
        rear_motor.data.motor_target_current_limit_min = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_min_max_speed,
            rear_motor.data.cfg.motor_current_limit_min_max,
            rear_motor.data.cfg.motor_current_limit_min_min)
        
        
        front_motor.data.battery_target_current_limit_max = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            front_motor.data.cfg.battery_current_limit_max_min_speed,
            front_motor.data.cfg.battery_current_limit_max_max,
            front_motor.data.cfg.battery_current_limit_max_min)
        
        rear_motor.data.battery_target_current_limit_max = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_max_min_speed,
            rear_motor.data.cfg.battery_current_limit_max_max,
            rear_motor.data.cfg.battery_current_limit_max_min)
        
        
        front_motor.data.battery_target_current_limit_min = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            front_motor.data.cfg.battery_current_limit_min_max_speed,
            front_motor.data.cfg.battery_current_limit_min_max,
            front_motor.data.cfg.battery_current_limit_min_min)
        
        
        rear_motor.data.battery_target_current_limit_min = simpleio.map_range(
            rear_motor.data.wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_min_max_speed,
            rear_motor.data.cfg.battery_current_limit_min_max,
            rear_motor.data.cfg.battery_current_limit_min_min)
        
        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.1)
        
wheel_speed_previous_motor_speed_erpm = 0
async def task_various():
    global rear_motor
    global wheel_speed_previous_motor_speed_erpm
    
    while True:

        # calculate the rear motor wheel speed
        if rear_motor.data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = rear_motor.data.speed_erpm
        
            # Fiido Q1S with installed Luneye motor 2000W
            # calculate the wheel speed in km/h
            perimeter = 6.28 * rear_motor.data.cfg.wheel_radius # 2*pi = 6.28
            motor_rpm = rear_motor.data.speed_erpm / rear_motor.data.cfg.poles_pair
            rear_motor.data.wheel_speed = ((perimeter / 1000.0) * motor_rpm * 60.0)

            if abs(rear_motor.data.wheel_speed < 2.0):
                rear_motor.data.wheel_speed = 0.0

        gc.collect() # https://learn.adafruit.com/Memory-saving-tips-for-CircuitPython
        await asyncio.sleep(0.1)
        
        
async def main():

    # setup watchdog, to reset the system if watchdog is not feed in time
    # 1 second is the min timeout possible, should be more than enough as task_control_motor() feeds the watchdog
    watchdog.timeout = 1
    watchdog.mode = WatchDogMode.RESET

    motors_refresh_data_task = asyncio.create_task(task_motors_refresh_data())
    control_motor_limit_current_task = asyncio.create_task(task_control_motor_limit_current())
    control_motor_task = asyncio.create_task(task_control_motor())
    display_send_data_task = asyncio.create_task(task_display_send_data())
    display_receive_process_data_task = asyncio.create_task(task_display_receive_process_data())
    various_task = asyncio.create_task(task_various())

    print("Starting EBike/EScooter")
    print()

    await asyncio.gather(motors_refresh_data_task,
                        display_send_data_task,
                        display_receive_process_data_task,
                        control_motor_limit_current_task,
                        control_motor_task,
                        various_task)

asyncio.run(main())




