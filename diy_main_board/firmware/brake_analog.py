from machine import ADC, Pin
import utils

class BrakeAnalog:
    """Brake input via ADC"""
    def __init__(self, adc_pin, min_val=32767, max_val=65535):
        """
        :param int adc_pin: GPIO number used for brake ADC
        :param int min_val: the min ADC value (usually ~1/2 of full scale)
        :param int max_val: the max ADC value (usually 65535)
        """
        self._adc = ADC(Pin(adc_pin))
        self._min = min_val
        self._max = max_val
        self._adc_previous_value = 0

    @property
    def adc_value(self):
        """Raw ADC value [0–65535]"""
        return self._adc.read_u16()

    @property
    def value(self):
        """Scaled brake value [0–1000]"""
        raw = self._adc.read_u16()
        return utils.map_range(raw, self._min, self._max, 0, 1000, clamp=True)
