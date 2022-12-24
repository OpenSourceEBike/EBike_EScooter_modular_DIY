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

vesc_data = VescData()
vesc = vesc.Vesc(
    board.IO14, #UART TX pin that connect to VESC
    board.IO13, #UART RX pin that connect to VESC
    vesc_data) #VESC data object to hold the VESC data

display = display.Display(
    board.IO12, #UART TX pin that connect to display
    board.IO11, #UART RX pin that connect to display
    vesc_data)

def check_brakes():
    if brake_sensor.value == True:
        vesc.set_current_amps(0)
        vesc_data.current_cut = True
    else:
        vesc_data.current_cut = False

async def task_display_process():
    while True:
        check_brakes()
      
        display.process_data()
        await asyncio.sleep(0.02) # idle 20ms, fine tunned

async def task_vesc_heartbeat():
    while True:
        check_brakes()

        # VESC heart beat must be sent more frequently than 1 second, otherwise the motor will stop
        vesc.send_heart_beat() 

        # ask for VESC latest data
        vesc.refresh_data()

        torque, cadence = torque_sensor.weight_value
        if torque is not None:
          print(f"tor {torque}")
          print(f"cad {cadence}")
        
        if brake_sensor.value:
          print("brk 1")
        else:
          print("brk 0")

        print(f"mot curr {vesc_data.battery_current:.1f}")

        print(" ")

        await asyncio.sleep(0.5) # idle 500ms

async def task_read_sensors_control_motor():
    while True:
        # check if brakes are active and if so, set motor current to 0 amps
        check_brakes()
      
        # read torque sensor data and map to motor current
        torque_weight_kgs, cadence = torque_sensor.weight_value
        if torque_weight_kgs is not None:
            motor_current = simpleio.map_range(
                torque_weight_kgs,
                2.0, # min kgs
                10.0, # up to max of 10 kgs
                0, # min motor current
                5.0) # max motor current
        else:
            motor_current = 0

        # only update the motor current if the value did change as also if brakes are not active
        if motor_current != vesc_data.previous_current:
          if vesc_data.current_cut == False:
            vesc_data.previous_current = motor_current
            vesc.set_current_amps(motor_current)

        await asyncio.sleep(0.02) # idle 20ms

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
