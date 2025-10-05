from machine import Pin

class Brake:
    """Brake sensor"""
    def __init__(self, pin):
        """
        :param pin: IO pin number used to read brake sensor
        """
        # configure IO input with pull-up (brake switch usually active low)
        self._brake = Pin(pin, Pin.IN, Pin.PULL_UP)

    @property
    def value(self):
        # return True if brake is pressed (inverted logic)
        return not self._brake.value()
