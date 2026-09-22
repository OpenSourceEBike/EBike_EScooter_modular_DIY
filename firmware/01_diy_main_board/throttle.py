from machine import ADC, Pin


def _scale_adc_to_throttle(raw, minimum, maximum):
  """Map an ADC reading to 0..1000 using only small integer operations."""
  if raw <= minimum:
    return 0
  if raw >= maximum:
    return 1000
  return ((raw - minimum) * 1000) // (maximum - minimum)

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
    self.raw_value = 0
    self.scaled_value = 0

  def refresh(self):
    """Read the ADC without creating the compatibility ``value`` tuple."""
    raw = self._adc.read_u16()
    self.raw_value = raw
    self.scaled_value = _scale_adc_to_throttle(raw, self._min, self._max)

  @property
  def value(self):
    # Keep the original public API for the slower callers, while the 20 ms
    # motor-control loop uses refresh() and the cached scalar attributes.
    self.refresh()
    return self.raw_value, self.scaled_value
