import simpleio
import adafruit_thermistor

class MotorTemperatureSensor(object):
    def __init__(self, motor_temeprature_sensor_pin):

        resistor = 1000
        resistance = 1000
        nominal_temp = 25
        b_coefficient = 3950

        self._thermistor = adafruit_thermistor.Thermistor(
            motor_temeprature_sensor_pin,
            resistor,
            resistance,
            nominal_temp,
            b_coefficient)

    @property
    def value(self):
        return self._thermistor.temperature