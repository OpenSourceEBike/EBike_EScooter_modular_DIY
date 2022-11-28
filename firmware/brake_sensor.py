import digitalio

class BrakeSensor(object):
    """Brake sensor"""
    def __init__(self, pin):
        """Brake sensor
        :param ~microcontroller.Pin pin: IO pin used to read brake sensor
        """
        # configure IO input
        self.__brake = digitalio.DigitalInOut(pin)
        self.__brake.pull = digitalio.Pull.UP
        self.__brake.direction = digitalio.Direction.INPUT

    @property
    def value(self):
        return self.__brake.value
