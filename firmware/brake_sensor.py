import digitalio

class brake_sensor(object):
    """Brake sensor"""
    def __init__(self, pin):
        """Brake sensor
        :param ~microcontroller.Pin pin: IO pin used to read brake sensor
        """
        # configure IO input
        self.brake = digitalio.DigitalInOut(pin)
        self.brake.pull = digitalio.Pull.UP
        self.brake.direction = digitalio.Direction.INPUT

    @property
    def value(self):
        return self.brake.value
