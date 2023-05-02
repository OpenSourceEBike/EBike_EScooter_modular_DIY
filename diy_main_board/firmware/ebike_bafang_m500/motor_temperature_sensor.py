import adafruit_thermistor

class MotorTemperatureSensor(object):
    def __init__(self, motor_temperature_sensor_pin):

        resistor = 1000
        resistance = 1000
        nominal_temp = 10
        b_coefficient = 3800

        self._thermistor = adafruit_thermistor.Thermistor(
            motor_temperature_sensor_pin,
            resistor,
            resistance,
            nominal_temp,
            b_coefficient,
            high_side = True)

    @property
    def value_x10(self):
        return int(self._thermistor.temperature * 10)