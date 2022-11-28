import board
import simpleio
import asyncio
import throttle
import brake_sensor
import wheel_speed_sensor
import torque_sensor
import vesc
from vesc import VescData
import display

brake_sensor = brake_sensor.BrakeSensor(
    board.P0_02) #brake sensor pin

wheel_speed_sensor = wheel_speed_sensor.WheelSpeedSensor(
    board.P1_15) #wheel speed sensor pin

torque_sensor = torque_sensor.TorqueSensor(
    board.P0_20, #SPI CS pin
    board.P0_17, #SPI clock pin
    board.P0_15, #SPI MOSI pin
    board.P0_13) #SPI MISO pin

throttle = throttle.Throttle(
    board.P0_29, #ADC pin for throttle
    min = 17500) #min ADC value that throttle reads, plus some margin

vesc_motor_data = VescData()
vesc = vesc.Vesc(
    board.P0_22, #UART TX pin that connect to VESC
    board.P0_24, #UART RX pin that connect to VESC
    vesc_motor_data) #VESC motor data object to hold the motor data

display = display.Display(
    board.P0_09, #UART TX pin that connect to display
    board.P0_10) #UART RX pin that connect to display

async def task_display_process():
    while True:
        display.process_data()
        await asyncio.sleep(0.05) # idle 50ms

async def task_vesc_heartbeat():
    while True:
        vesc.send_heart_beat()
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
    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    read_sensors_control_motor_task = asyncio.create_task(task_read_sensors_control_motor())
    display_process_task = asyncio.create_task(task_display_process())
    await asyncio.gather(
        vesc_heartbeat_task,
        read_sensors_control_motor_task,
        display_process_task)
    print("done main()")

asyncio.run(main())
