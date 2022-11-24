from time import sleep
import throttle
import torque_sensor

torque_sensor = torque_sensor.torque_sensor()
throttle = throttle.throttle(17500)

while True:
    torque, cadence = torque_sensor.read()
    if torque is not None:
        print("Torque: " + str(torque))
        print("Cadence: " + str(cadence))

    throttle_value = throttle.read()
    print("Throttle: " + str(throttle_value))
    print(" ")

    sleep(1)
