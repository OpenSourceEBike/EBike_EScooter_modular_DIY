import board
import time
import throttle
import brake
import wheel_speed_sensor
import torque_sensor
import motor_temperature_sensor

# Tested on a ESP32-S3-DevKitC-1-N8R2

brake = brake.Brake(
   board.IO10) # brake sensor pin

wheel_speed_sensor = wheel_speed_sensor.WheelSpeedSensor(
   board.IO46) # wheel speed sensor pin

torque_sensor = torque_sensor.TorqueSensor(
    board.IO4, # CAN tx pin
    board.IO5) # CAN rx pin
  
throttle = throttle.Throttle(
    board.IO18, # ADC pin for throttle
    min = 17000, # min ADC value that throttle reads, plus some margin
    max = 50000) # max ADC value that throttle reads, minus some margin

motor_temperature_sensor = motor_temperature_sensor.MotorTemperatureSensor(
   board.IO3) # motor temperature sensor pin

print("starting")

while True:
    print(" ")

    # read torque sensor data and print
    torque, cadence = torque_sensor.torque_value
    if torque is not None:
        print(f"torque sensor raw value: {torque}")
        print(f"torque sensor cadence: {cadence} rpm")
    else:
        print(f"can not read torque sensor")

    # brake sensor
    brake = "enable" if brake.value == True else "disable"
    print(f"brake sensor state: {brake}")

    # throttle sensor
    print(f"throttle raw value: {throttle.adc_value}")

    # wheel speed sensor
    wheel_speed = "enable" if wheel_speed_sensor.value == True else "disable"
    print(f"wheel speed sensor state: {wheel_speed}")

    # motor temperature sensor
    print(f"motor temperature sensor: {motor_temperature_sensor.value :0.1f} ºC")

    # wait some time before repeat
    time.sleep(1)
