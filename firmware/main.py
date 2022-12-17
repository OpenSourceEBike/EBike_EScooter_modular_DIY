import board
import time
import simpleio
import asyncio
import throttle
import brake_sensor
import wheel_speed_sensor
import torque_sensor
import vesc
from vesc import VescData
import display

# Tested on a ESP32-S3-DevKitC-1-N8R2

brake_sensor = brake_sensor.BrakeSensor(
    board.IO1) #brake sensor pin

wheel_speed_sensor = wheel_speed_sensor.WheelSpeedSensor(
    board.IO42) #wheel speed sensor pin

torque_sensor = torque_sensor.TorqueSensor(
    board.IO0, #SPI CS pin
    board.IO35, #SPI clock pin
    board.IO36, #SPI MOSI pin
    board.IO37) #SPI MISO pin

throttle = throttle.Throttle(
    board.IO2, #ADC pin for throttle
    min = 17500) #min ADC value that throttle reads, plus some margin

vesc_data = VescData()
vesc = vesc.Vesc(
    board.IO21, #UART TX pin that connect to VESC
    board.IO47, #UART RX pin that connect to VESC
    vesc_data) #VESC data object to hold the VESC data

display = display.Display(
    board.IO48, #UART TX pin that connect to display
    board.IO45, #UART RX pin that connect to display
    vesc_data)

async def task_display_process():
    while True:
        display.process_data()
        await asyncio.sleep(0.02) # idle 20ms, fine tunned

async def task_vesc_heartbeat():
    while True:
        # VESC heart beat must be sent more frequently than 1 second, otherwise the motor will stop
        vesc.send_heart_beat() 

        # ask for VESC latest data
        vesc.refresh_data()

        await asyncio.sleep(0.8) # idle 800ms

async def task_read_sensors_control_motor():
    while True:
        # read throttle and map to motor current
        motor_current = simpleio.map_range(
            throttle.value, #[0 - 1000]
            0, #min throttle
            1000, #max throttle
            0, #min current
            5.0) #max current

        vesc.set_current_brake_amps(0.0)
        vesc.set_current_amps(motor_current)

        await asyncio.sleep(0.002) # idle 20ms

async def main():

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
