import digitalio

class BrakeSensor(object):
    """Brake sensor"""
    def __init__(self, pin):
        """Brake sensor
        :param ~microcontroller.Pin pin: IO pin used to read brake sensor
        """
        # configure IO input
        # NOTE about pull up: the ESP32 internal pullups are weak and are not enough for the brake sensor
        self.__brake = digitalio.DigitalInOut(pin)
        self.__brake.direction = digitalio.Direction.INPUT

    @property
    def value(self):
        return not self.__brake.value # brake signal is inverted