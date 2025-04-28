import analogio
import simpleio

class BrakeAnalog(object):
    """Throttle"""
    def __init__(self, adc_pin, min = 65535/2, max = 65535):
        """Throttle
        :param ~microcontroller.Pin adc_pin: ADC pin used for brake
        :param int min: the min ADC value (should be a little higher than brake lowest value)
        :param max min: the max ADC value, usually 65535. Defaults to 65535.
        """
        self._adc = analogio.AnalogIn(adc_pin)
        self._min = min
        self._max = max
        self._adc_previous_value = 0

    @property
    def adc_value(self):
        """Read the brake ADC value
        return: brake ADC value
        """
        # read ADC value
        return self._adc.value

    @property
    def value(self):
        """Read the brake
        return: brake [0 - 1000]
        """
        
        # map brake to 0 --> 1000
        brake = int(simpleio.map_range(self._adc.value, self._min, self._max, 0, 1000))
        return brake