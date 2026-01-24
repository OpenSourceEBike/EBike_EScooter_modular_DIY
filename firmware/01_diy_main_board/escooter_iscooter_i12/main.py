import time
import gc
import uasyncio as asyncio

import neopixel
import machine
from machine import WDT
from vars import Vars
from motor import MotorData, Motor
from common.config_runtime import cfg, rear_motor_cfg
from brake import Brake
from throttle import Throttle
from common.utils import map_range
import escooter_iscooter_i12.display_espnow as DisplayESPnow
from mode import Mode

led = neopixel.NeoPixel(machine.Pin(21, machine.Pin.OUT), 1)

# Object that holds various runtime variables
vars = Vars()

# Brake sensor
brake_sensor = Brake(cfg.brake_pin)

# If brakes are active at startup, block here (development safety)
while brake_sensor.value:
    print('brake at start')
    time.sleep(1)

# Motors: data + driver objects
rear_motor_data  = MotorData(rear_motor_cfg)
rear_motor  = Motor(rear_motor_data)

# Init targets from configuration
rear_motor.data.motor_target_current_limit_max = rear_motor.data.cfg.motor_max_current_limit_max
rear_motor.data.motor_target_current_limit_min = rear_motor.data.cfg.motor_max_current_limit_min
rear_motor.data.battery_target_current_limit_max = rear_motor.data.cfg.battery_max_current_limit_max
rear_motor.data.battery_target_current_limit_min = rear_motor.data.cfg.battery_max_current_limit_min

# ESP-NOW display link
display = DisplayESPnow.Display(vars, rear_motor.data, cfg.display_mac_address)

# Throttles
throttle_1 = Throttle(
    cfg.throttle_1_pin,
    min_val=cfg.throttle_1_adc_min,   # min ADC (with margin)
    max_val=cfg.throttle_1_adc_max,   # max ADC (with margin)
)

mode = Mode(brake_sensor, throttle_1, vars, save_to_nvs=cfg.save_mode_to_nvs)

# ─────────────────────────────────────────────────────────────────────────────
# Optional BMS support (BLE) — BLE activation is deferred to bms.start()
# ─────────────────────────────────────────────────────────────────────────────
if cfg.has_jbd_bms:
    import bluetooth
    from bms_jbd import JbdBmsClient

    # Create a single BLE instance; don't call active(True) here.
    ble = bluetooth.BLE()
    bms = JbdBmsClient(
        ble=ble,
        target_name=cfg.jbd_bms_bluetooth_name,
        query_period_ms=1000,
        interleave_cells=True,
        debug=True,
    )

    async def bms_task(bms: JbdBmsClient):
        """
        Drive the client's cooperative state machine:
        - drain BLE notifications
        - schedule 0x03/0x04 polls
        - keep reconnect logic responsive
        NOTE: we start BLE only after ESP-NOW is up and we've paused briefly.
        """
        # Give Wi-Fi/ESP-NOW a moment to settle before starting BLE (coex-friendly)
        await asyncio.sleep_ms(300)
        bms.start(scan_ms=8000)  # start() will activate BLE with small retries
        while True:
            bms.tick()
            await asyncio.sleep_ms(50)  # ~20 Hz tick

    async def bms_read_task(bms: JbdBmsClient):
        """
        Periodically read cached data. No blocking, no BLE calls here.
        """
        while True:
            if bms.is_connected() and bms.is_fresh(3000):
                vars.bms_battery_current_x100 = bms.get_current_a_x100()
            await asyncio.sleep_ms(1000)  # read cadence

async def task_motors_refresh_data():
    # Refresh latest VESC data (call once; it fills both via CAN)
    while True:
        rear_motor.update_motor_data(rear_motor, None)
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
        motor_erpm_max_speed_limit = rear_motor.data.cfg.motor_erpm_max_speed_limit[vars.mode]
        
        # Throttle: take max of the two
        throttle_1_adc_value, throttle_1_value = throttle_1.value
        throttle_value = throttle_1_value
        
        # print(throttle_1_adc_value, throttle_1_value)
        # print()
        
        # Over-max safety (ADC glitch protection)
        if (throttle_1_adc_value > cfg.throttle_1_adc_over_max_error):
            # Send zero current a few times to be safe
            for _ in range(3):
                rear_motor.set_motor_current_amps(0)

            if throttle_1_adc_value > cfg.throttle_1_adc_over_max_error:
                raise Exception(
                    f'throttle 1 adc: {throttle_1_adc_value} -- is over max, this can be dangerous!'
                )

        # Cruise control
        throttle_value = cruise_control(vars, rear_motor.data.wheel_speed, throttle_value)

        # Target speed (map 0..1000 → 0..ERPM limit)
        rear_motor.data.motor_target_speed = map_range(
            throttle_value, 0.0, 1000.0, 0.0, motor_erpm_max_speed_limit, clamp=True
        )

        # Small dead-zone
        if rear_motor.data.motor_target_speed < 500.0:
            rear_motor.data.motor_target_speed = 0.0

        # Enforce max
        if rear_motor.data.motor_target_speed > motor_erpm_max_speed_limit:
            rear_motor.data.motor_target_speed = motor_erpm_max_speed_limit

        # Set motor/battery current limits
        rear_motor.set_motor_current_limits(
            rear_motor.data.motor_target_current_limit_min,
            rear_motor.data.motor_target_current_limit_max)

        rear_motor.set_battery_current_limits(
            rear_motor.data.battery_target_current_limit_min,
            rear_motor.data.battery_target_current_limit_max)

        # Brakes
        vars.brakes_are_active = True if brake_sensor.value else False

        # Command motor(s)        
        if vars.motors_enable_state is False:
            rear_motor.set_motor_current_amps(0)
        else:
            if vars.brakes_are_active:
                rear_motor.set_motor_speed_rpm(0)
            else:
                rear_motor.set_motor_speed_rpm(rear_motor.data.motor_target_speed)

        # Feed watchdog
        wdt.feed()

        gc.collect()
        await asyncio.sleep(0.02)

async def task_control_motor_limit_current():
    while True:
        # Always use rear wheel speed
        wheel_speed = rear_motor.data.wheel_speed

        rear_motor.data.motor_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_max_min_speed,
            rear_motor.data.cfg.motor_current_limit_max_max,
            rear_motor.data.cfg.motor_current_limit_max_min,
            clamp=True)

        rear_motor.data.motor_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.motor_current_limit_min_max_speed,
            rear_motor.data.cfg.motor_current_limit_min_max,
            rear_motor.data.cfg.motor_current_limit_min_min,
            clamp=True)

        rear_motor.data.battery_target_current_limit_max = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_max_min_speed,
            rear_motor.data.cfg.battery_current_limit_max_max,
            rear_motor.data.cfg.battery_current_limit_max_min,
            clamp=True)

        rear_motor.data.battery_target_current_limit_min = map_range(
            wheel_speed,
            5.0,
            rear_motor.data.cfg.battery_current_limit_min_max_speed,
            rear_motor.data.cfg.battery_current_limit_min_max,
            rear_motor.data.cfg.battery_current_limit_min_min,
            clamp=True)

        gc.collect()
        await asyncio.sleep(0.025)

wheel_speed_previous_motor_speed_erpm = 0

led_state = False
def led_blink():
    global led_state
    
    led_state = not led_state
    if led_state:
        led[0] = (0, 4, 0)
    else:
        led[0] = (4, 0, 0)
        
    led.write()

async def task_various():
    global wheel_speed_previous_motor_speed_erpm
    global mode
    
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
                
        # Run Mode tick
        mode.tick()
        
        led_blink()

        gc.collect()
        await asyncio.sleep(0.1)

async def main():
    # Watchdog (min 1s on ESP32). task_control_motor() feeds it continuously.
    wdt = WDT(timeout=1000)

    # Build the task list
    tasks = [
        asyncio.create_task(task_motors_refresh_data()),
        asyncio.create_task(task_control_motor_limit_current()),
        asyncio.create_task(task_control_motor(wdt)),
        asyncio.create_task(task_display_send_data()),
        asyncio.create_task(task_display_receive_process_data()),
        asyncio.create_task(task_various()),
    ]

    # Add BMS tasks only if enabled in config
    if cfg.has_jbd_bms:
        tasks.append(asyncio.create_task(bms_task(bms)))
        tasks.append(asyncio.create_task(bms_read_task(bms)))

    print("Starting EBike/EScooter\n")

    # Wait for all tasks (keeps main alive; propagates exceptions)
    await asyncio.gather(*tasks)

asyncio.run(main())
