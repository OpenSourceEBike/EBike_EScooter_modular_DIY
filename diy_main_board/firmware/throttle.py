import analogio
import simpleio

class Throttle(object):
    """Throttle"""
    def __init__(self, adc_pin, min = 65535/2, max = 65535):
        """Throttle
        :param ~microcontroller.Pin adc_pin: ADC pin used for throttle
        :param int min: the min ADC value (should be a little higher than throttle lowest value)
        :param max min: the max ADC value, usually 65535. Defaults to 65535.
        """
        self._adc = analogio.AnalogIn(adc_pin)
        self._min = min
        self._max = max
        self._adc_previous_value = 0

    @property
    def adc_value(self):
        """Read the throttle ADC value
        return: throttle ADC value
        """
        # read ADC value
        return self._adc.value

    @property
    def value(self):
        """Read the throttle
        return: throttle [0 - 1000]
        """
        
        # map throttle to 0 --> 1000
        throttle = int(simpleio.map_range(self._adc.value, self._min, self._max, 0, 1000))
        return throttle