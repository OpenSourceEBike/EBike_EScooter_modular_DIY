from machine import ADC, Pin
from firmware_common.utils import map_range

class Throttle:
    """Throttle input via ADC"""
    def __init__(self, adc_pin, min_val=32767, max_val=65535):
        """
        :param int adc_pin: GPIO number for throttle ADC
        :param int min_val: minimum ADC value (slightly above rest)
        :param int max_val: maximum ADC value (slightly below full)
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
        """Scaled throttle [0–1000]"""
        raw = self._adc.read_u16()
        return int(map_range(raw, self._min, self._max, 0, 1000, clamp=True))
