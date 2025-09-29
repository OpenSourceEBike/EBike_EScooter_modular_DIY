import time
import gc
import uasyncio as asyncio

from machine import WDT
from vars import Vars
from motor import MotorData, Motor
from configurations_escooter_fiido_q1_s import cfg, front_motor_cfg, rear_motor_cfg
from brake import Brake
from throttle import Throttle
from firmware_common.utils import map_range
import escooter_fiido_q1_s.display_espnow as DisplayESPnow


# Object that holds various runtime variables
vars = Vars()

# Brake sensor
brake_sensor = Brake(cfg.brake_pin)

# If brakes are active at startup, block here (development safety)
while brake_sensor.value:
    print('brake at start')
    time.sleep(1)

# Motors: data + driver objects
front_motor_data = MotorData(front_motor_cfg)
rear_motor_data  = MotorData(rear_motor_cfg)
front_motor = Motor(front_motor_data)
rear_motor  = Motor(rear_motor_data)

# Init targets from configuration
front_motor.data.motor_target_current_limit_max = front_motor.data.cfg.motor_max_current_limit_max
front_motor.data.motor_target_current_limit_min = front_motor.data.cfg.motor_max_current_limit_min
front_motor.data.battery_target_current_limit_max = front_motor.data.cfg.battery_max_current_limit_max
front_motor.data.battery_target_current_limit_min = front_motor.data.cfg.battery_max_current_limit_min

rear_motor.data.motor_target_current_limit_max = rear_motor.data.cfg.motor_max_current_limit_max
rear_motor.data.motor_target_current_limit_min = rear_motor.data.cfg.motor_max_current_limit_min
rear_motor.data.battery_target_current_limit_max = rear_motor.data.cfg.battery_max_current_limit_max
rear_motor.data.battery_target_current_limit_min = rear_motor.data.cfg.battery_max_current_limit_min

# ESP-NOW display link
display = DisplayESPnow.Display(vars, front_motor.data, rear_motor.data, cfg.display_mac_address)

# Throttles
throttle_1 = Throttle(
    cfg.throttle_1_pin,
    min_val=cfg.throttle_1_adc_min,   # min ADC (with margin)
    max_val=cfg.throttle_1_adc_max,   # max ADC (with margin)
)

throttle_2 = Throttle(
    cfg.throttle_2_pin,
    min_val=cfg.throttle_2_adc_min,
    max_val=cfg.throttle_2_adc_max,
)

async def task_motors_refresh_data():
    # Refresh latest VESC data (call once; it fills both via CAN)
    while True:
        rear_motor.update_motor_data(rear_motor, front_motor)
        gc.collect()
        await asyncio.sleep(0.05)

async def task_display_send_data():
    while True:
        display.send_data()
        gc.collect()
        await asyncio.sleep(0.25)

async def task_display_receive_process_data():
    while True:
        display.receive_process_data()
        gc.collect()
        await asyncio.sleep(0.1)

def cruise_control(vars, wheel_speed, throttle_value):
    button_long_press_state = vars.buttons_state & 0x0200

    # Init
    if vars.cruise_control.state == 0:
        vars.cruise_control.button_long_press_previous_state = button_long_press_state
        vars.cruise_control.state = 1

    # Wait to start cruise
    if vars.cruise_control.state == 1:
        if (button_long_press_state != vars.cruise_control.button_long_press_previous_state) and (wheel_speed > 4.0):
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            vars.cruise_control.throttle_value = throttle_value
            vars.cruise_control.state = 2

    # Cruise active
    if vars.cruise_control.state == 2:
        vars.cruise_control.button_pressed = False
        button_press_state = vars.buttons_state & 0x0100
        if button_press_state != vars.cruise_control.button_press_previous_state:
            vars.cruise_control.button_press_previous_state = button_press_state
            vars.cruise_control.button_pressed = True

        # Stop cruise?
        if vars.brakes_are_active or vars.cruise_control.button_pressed or throttle_value > (vars.cruise_control.throttle_value * 1.15):
            vars.cruise_control.button_long_press_previous_state = button_long_press_state
            vars.cruise_control.state = 1
        else:
            # Keep cruising: override throttle
            throttle_value = vars.cruise_control.throttle_value

    return throttle_value

async def task_control_motor(wdt):
    while True:
        # Throttle: take max of the two
        throttle_1_value = throttle_1.value
        throttle_2_value = throttle_2.value
        throttle_value = max(throttle_1_value, throttle_2_value)
        
        #print(throttle_1.adc_value, throttle_2.adc_value)
        #print(throttle_value)

        # Over-max safety (ADC glitch protection)
        if (throttle_1_value > cfg.throttle_1_adc_over_max_error) or \
           (throttle_2_value > cfg.throttle_2_adc_over_max_error):
            # Send zero current a few times to be safe
            for _ in range(3):
                front_motor.set_motor_current_amps(0)
                rear_motor.set_motor_current_amps(0)

            if throttle_1_value > cfg.throttle_1_adc_over_max_error:
                raise Exception(f'throttle 1 value: {throttle_1_value} -- is over max, this can be dangerous!')
            else:
                raise Exception(f'throttle 2 value: {throttle_2_value} -- is over max, this can be dangerous!')

        # Cruise control
        throttle_value = cruise_control(vars, rear_motor.data.wheel_speed, throttle_value)

        # Target speed (map 0..1000 → 0..ERPM limit)
        front_motor.data.motor_target_speed = map_range(
            throttle_value, 0.0, 1000.0, 0.0, front_motor.data.cfg.motor_erpm_max_speed_limit, clamp=True
        )
        rear_motor.data.motor_target_speed = map_range(
            throttle_value, 0.0, 1000.0, 0.0, rear_motor.data.cfg.motor_erpm_max_speed_limit, clamp=True
        )

        # Small dead-zone
        if front_motor.data.motor_target_speed < 500.0:
            front_motor.data.motor_target_speed = 0.0
        if rear_motor.data.motor_target_speed < 500.0:
            rear_motor.data.motor_target_speed = 0.0

        # Enforce max
        if front_motor.data.motor_target_speed > front_motor.data.cfg.motor_erpm_max_speed_limit:
            front_motor.data.motor_target_speed = front_motor.data.cfg.motor_erpm_max_speed_limit
        if rear_motor.data.motor_target_speed > rear_motor.data.cfg.motor_erpm_max_speed_limit:
            rear_motor.data.motor_target_speed = rear_motor.data.cfg.motor_erpm_max_speed_limit

        # Set motor/battery current limits
        front_motor.set_motor_current_limits(
            front_motor.data.motor_target_current_limit_min,
            front_motor.data.motor_target_current_limit_max)
        rear_motor.set_motor_current_limits(
            rear_motor.data.motor_target_current_limit_min,
            rear_motor.data.motor_target_current_limit_max)

        front_motor.set_battery_current_limits(
            front_motor.data.battery_target_current_limit_min,
            front_motor.data.battery_target_current_limit_max)
        rear_motor.set_battery_current_limits(
            rear_motor.data.battery_target_current_limit_min,
            rear_motor.data.battery_target_current_limit_max)

        # Brakes
        vars.brakes_are_active = True if brake_sensor.value else False

        # Command motor(s)
        
        vars.motors_enable_state = True
        
        if not vars.motors_enable_state:
            front_motor.set_motor_current_amps(0)
            rear_motor.set_motor_current_amps(0)
        else:
            if vars.brakes_are_active:
                front_motor.set_motor_speed_rpm(0)
                rear_motor.set_motor_speed_rpm(0)
            else:
                front_motor.set_motor_speed_rpm(front_motor.data.motor_target_speed)
                rear_motor.set_motor_speed_rpm(rear_motor.data.motor_target_speed)
                
        # Feed watchdog
        #wdt.feed()

        gc.collect()
        await asyncio.sleep(0.02)

async def task_control_motor_limit_current():
    while True:
        # Always use rear wheel speed (front may skid)
        wheel_speed = rear_motor.data.wheel_speed

        front_motor.data.motor_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            front_motor.data.cfg.motor_current_limit_max_min_speed,
            front_motor.data.cfg.motor_current_limit_max_max,
            front_motor.data.cfg.motor_current_limit_max_min,
            clamp=True)
        rear_motor.data.motor_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_max_min_speed,
            rear_motor.data.cfg.motor_current_limit_max_max,
            rear_motor.data.cfg.motor_current_limit_max_min,
            clamp=True)

        front_motor.data.motor_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            front_motor.data.cfg.motor_current_limit_min_max_speed,
            front_motor.data.cfg.motor_current_limit_min_max,
            front_motor.data.cfg.motor_current_limit_min_min,
            clamp=True)
        rear_motor.data.motor_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_min_max_speed,
            rear_motor.data.cfg.motor_current_limit_min_max,
            rear_motor.data.cfg.motor_current_limit_min_min,
            clamp=True)

        front_motor.data.battery_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            front_motor.data.cfg.battery_current_limit_max_min_speed,
            front_motor.data.cfg.battery_current_limit_max_max,
            front_motor.data.cfg.battery_current_limit_max_min,
            clamp=True)
        rear_motor.data.battery_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_max_min_speed,
            rear_motor.data.cfg.battery_current_limit_max_max,
            rear_motor.data.cfg.battery_current_limit_max_min,
            clamp=True)

        front_motor.data.battery_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            front_motor.data.cfg.battery_current_limit_min_max_speed,
            front_motor.data.cfg.battery_current_limit_min_max,
            front_motor.data.cfg.battery_current_limit_min_min,
            clamp=True)
        rear_motor.data.battery_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_min_max_speed,
            rear_motor.data.cfg.battery_current_limit_min_max,
            rear_motor.data.cfg.battery_current_limit_min_min,
            clamp=True)

        gc.collect()
        await asyncio.sleep(0.1)

wheel_speed_previous_motor_speed_erpm = 0
async def task_various():
    global wheel_speed_previous_motor_speed_erpm
    while True:
        # Calculate rear motor wheel speed
        if rear_motor.data.speed_erpm != wheel_speed_previous_motor_speed_erpm:
            wheel_speed_previous_motor_speed_erpm = rear_motor.data.speed_erpm

            # 2*pi ≈ 6.28318
            perimeter = 6.28318 * rear_motor.data.cfg.wheel_radius  # meters
            motor_rpm = rear_motor.data.speed_erpm / max(1, rear_motor.data.cfg.poles_pair)
            rear_motor.data.wheel_speed = (perimeter * motor_rpm * 60.0) / 1000.0  # km/h

            # Small floor near zero
            if abs(rear_motor.data.wheel_speed) < 2.0:
                rear_motor.data.wheel_speed = 0.0

        gc.collect()
        await asyncio.sleep(0.1)
        
async def main():
    # Watchdog (min 1s on ESP32). task_control_motor() feeds it continuously.
    #wdt = WDT(timeout=1000)
    wdt=None
    
    await display.start()

    motors_refresh_data_task       = asyncio.create_task(task_motors_refresh_data())
    control_motor_limit_current_task = asyncio.create_task(task_control_motor_limit_current())
    control_motor_task             = asyncio.create_task(task_control_motor(wdt))
    display_send_data_task         = asyncio.create_task(task_display_send_data())
    display_receive_process_data_task = asyncio.create_task(task_display_receive_process_data())
    various_task                   = asyncio.create_task(task_various())

    print("Starting EBike/EScooter\n")

    await asyncio.gather(
        motors_refresh_data_task,
        display_send_data_task,
        display_receive_process_data_task,
        control_motor_limit_current_task,
        control_motor_task,
        various_task
    )

asyncio.run(main())
