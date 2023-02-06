import digitalio

class Buttons(object):
    def __init__(self, power_pin, up_pin, down_pin):

        self._power = digitalio.DigitalInOut(power_pin)
        self._power.direction = digitalio.Direction.INPUT
        self._power.pull = digitalio.Pull.UP

        self._up = digitalio.DigitalInOut(up_pin)
        self._up.direction = digitalio.Direction.INPUT
        self._up.pull = digitalio.Pull.UP

        self._down = digitalio.DigitalInOut(down_pin)
        self._down.direction = digitalio.Direction.INPUT
        self._down.pull = digitalio.Pull.UP

    @property
    def power(self):
        return not self._power.value

    @property
    def up(self):
        return not self._up.value

    @property
    def down(self):
        return not self._down.value