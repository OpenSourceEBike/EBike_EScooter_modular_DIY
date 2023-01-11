import digitalio

class WheelSpeedSensor(object):
    """Wheel speed sensor"""
    def __init__(self, pin):
        """Wheel speed sensor
        :param ~microcontroller.Pin pin: IO pin used to read wheel speed sensor
        """
        # configure IO input
        self.__wheel_speed = digitalio.DigitalInOut(pin)
        self.__wheel_speed.pull = digitalio.Pull.UP
        self.__wheel_speed.direction = digitalio.Direction.INPUT

    @property
    def value(self):
        return not self.__wheel_speed.value
