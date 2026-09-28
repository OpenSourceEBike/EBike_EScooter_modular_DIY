"""Passive DC-resistance estimator using only new JBD BASIC samples."""

STATE_REFERENCE = 0
STATE_SETTLE = 1
STATE_LOAD = 2
STATE_COMPLETE = 3


def bms_resistance_rejection_reason(protections):
  """Return why a BMS sample must not be used for resistance measurement."""
  if protections:
    return 'BMS protection active'
  return ''


def _ticks_diff(newer_ms, older_ms):
  try:
    import time
    return time.ticks_diff(newer_ms, older_ms)
  except AttributeError:
    return newer_ms - older_ms


def _mean(samples, index):
  return sum(sample[index] for sample in samples) // len(samples)


class BmsBatteryResistanceEstimator:
  """Estimate sustained-load DC sag, not instantaneous cell impedance.

  JBD discharge current is negative. A result is accepted only after a stable
  low-power reference, a 750 W discharge, one discarded settling BASIC frame,
  and three sustained-load BASIC samples.
  """

  def __init__(self, config):
    self.config = config
    self.samples = []
    self.baseline = None
    self.load_samples = []
    self.last_timestamp_ms = None
    self.state = STATE_REFERENCE
    self.state_started_ms = 0
    self.event_started_ms = None

  def reset(self, timestamp_ms=0):
    self.samples = []
    self.baseline = None
    self.load_samples = []
    self.last_timestamp_ms = None
    self.state = STATE_REFERENCE
    self.state_started_ms = timestamp_ms
    self.event_started_ms = None

  def _set_state(self, state, timestamp_ms):
    self.state = state
    self.state_started_ms = timestamp_ms

  def _reset_to_reference(self, timestamp_ms):
    self.baseline = None
    self.load_samples = []
    self.event_started_ms = None
    self._set_state(STATE_REFERENCE, timestamp_ms)

  def _power_scaled(self, sample):
    # voltage/current are both x100, so this is W x10000 without rounding.
    return sample[1] * sample[2]

  def _is_reference_sample(self, sample):
    power_scaled = self._power_scaled(sample)
    return (
      self.config.reference_power_min_w * 10000 <= power_scaled <=
      self.config.reference_power_max_w * 10000
    )

  def _is_load_sample(self, sample):
    return self._power_scaled(sample) <= -self.config.load_power_min_w * 10000

  def _recent_reference_baseline(self):
    count = self.config.baseline_sample_count
    if len(self.samples) < count:
      return None
    recent = self.samples[-count:]
    if any(not self._is_reference_sample(sample) for sample in recent):
      return None
    return (_mean(recent, 1), _mean(recent, 2))

  def state_sample_progress(self):
    """Return completed/required samples for the phase shown by the UI."""
    if self.state == STATE_REFERENCE:
      count = 0
      for sample in reversed(self.samples):
        if not self._is_reference_sample(sample):
          break
        count += 1
        if count >= self.config.baseline_sample_count:
          break
      return (count, self.config.baseline_sample_count)
    if self.state == STATE_SETTLE:
      return (0, 1)
    if self.state == STATE_LOAD:
      return (len(self.load_samples), self.config.load_sample_count)
    if self.state == STATE_COMPLETE:
      return (self.config.load_sample_count, self.config.load_sample_count)
    return (0, 0)

  def update(self, timestamp_ms, voltage_x100, current_x100):
    """Consume one unique BASIC sample; return (mohm, metadata) or None."""
    if timestamp_ms == self.last_timestamp_ms:
      return None
    self.last_timestamp_ms = timestamp_ms
    sample = (timestamp_ms, int(voltage_x100), int(current_x100))
    self.samples.append(sample)
    if len(self.samples) > self.config.buffer_size:
      self.samples.pop(0)

    if (self.state in (STATE_SETTLE, STATE_LOAD) and
        self.event_started_ms is not None and
        _ticks_diff(timestamp_ms, self.event_started_ms) >
        self.config.load_event_max_ms):
      self._reset_to_reference(timestamp_ms)
      return None

    if self.state == STATE_COMPLETE:
      if self._is_reference_sample(sample):
        self._reset_to_reference(timestamp_ms)
      return None

    if self.state == STATE_REFERENCE:
      if self.baseline is not None and self._is_load_sample(sample):
        self.load_samples = []
        self._set_state(STATE_SETTLE, timestamp_ms)
        self.event_started_ms = timestamp_ms
        return None
      self.baseline = self._recent_reference_baseline()
      return None

    if self.state == STATE_SETTLE:
      # Discard the first BASIC frame after the detected step.
      if not self._is_load_sample(sample):
        self._reset_to_reference(timestamp_ms)
        return None
      self.load_samples = []
      self._set_state(STATE_LOAD, timestamp_ms)
      return None

    if not self._is_load_sample(sample):
      self._reset_to_reference(timestamp_ms)
      return None

    self.load_samples.append(sample)
    count = self.config.load_sample_count
    if len(self.load_samples) > count:
      self.load_samples.pop(0)
    if len(self.load_samples) < count:
      return None

    after_voltage_x100 = _mean(self.load_samples, 1)
    after_current_x100 = _mean(self.load_samples, 2)
    delta_voltage_x100 = self.baseline[0] - after_voltage_x100
    delta_current_x100 = abs(after_current_x100 - self.baseline[1])
    if delta_voltage_x100 < self.config.min_voltage_drop_x100:
      self._reset_to_reference(timestamp_ms)
      return None

    resistance_mohm = (
      (1000 * delta_voltage_x100 + delta_current_x100 // 2) //
      delta_current_x100
    )
    if not (self.config.min_mohm <= resistance_mohm <=
            self.config.max_mohm):
      self._reset_to_reference(timestamp_ms)
      return None

    metadata = {
      'before_voltage_x100': self.baseline[0],
      'before_current_x100': self.baseline[1],
      'after_voltage_x100': after_voltage_x100,
      'after_current_x100': after_current_x100,
      'delta_voltage_x100': delta_voltage_x100,
      'delta_current_x100': delta_current_x100,
      'load_current_min_x100': min(sample[2] for sample in self.load_samples),
      'load_current_max_x100': max(sample[2] for sample in self.load_samples),
    }
    self._set_state(STATE_COMPLETE, timestamp_ms)
    return resistance_mohm, metadata
