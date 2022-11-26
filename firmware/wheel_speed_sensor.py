import digitalio

class wheel_speed_sensor(object):
    """Wheel speed sensor"""
    def __init__(self, pin):
        """Wheel speed sensor
        :param ~microcontroller.Pin pin: IO pin used to read wheel speed sensor
        """
        # configure IO input
        self.wheel_speed = digitalio.DigitalInOut(pin)
        self.wheel_speed.pull = digitalio.Pull.UP
        self.wheel_speed.direction = digitalio.Direction.INPUT

    @property
    def value(self):
        return self.wheel_speed.value

