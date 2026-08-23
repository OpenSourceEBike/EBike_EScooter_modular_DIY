import time


def _is_plain_int(value):
  return isinstance(value, int) and not isinstance(value, bool)


def aggregate_battery_measurements(pairs):
  """Combine per-VESC (voltage_x10, current_x10) into one x100 sample."""
  total_current_x10 = 0
  weighted_voltage_numerator = 0
  voltage_sum_x10 = 0
  voltage_count = 0
  try:
    for voltage_x10, current_x10 in pairs:
      if not (_is_plain_int(voltage_x10) and
              _is_plain_int(current_x10)):
        return None
      if current_x10 < 0:
        return None
      if voltage_x10 <= 0:
        return None
      total_current_x10 += current_x10
      weighted_voltage_numerator += voltage_x10 * current_x10
      voltage_sum_x10 += voltage_x10
      voltage_count += 1
  except (TypeError, ValueError, OverflowError):
    return None
  if total_current_x10 == 0:
    return (voltage_sum_x10 // voltage_count) * 10, 0
  weighted_voltage_x10 = weighted_voltage_numerator // total_current_x10
  if weighted_voltage_x10 <= 0:
    return None
  return weighted_voltage_x10 * 10, total_current_x10 * 10


class BatteryResistanceMonitor:
  """One passive result per boot from irregular, validated aggregate samples."""

  _BOOT = 0
  _REFERENCE_QUALIFY = 1
  _LOAD_QUALIFY = 2
  _COMPLETE = 3

  def __init__(self, config, sample_scale=100):
    if (not _is_plain_int(sample_scale) or sample_scale < 100 or
        sample_scale % 100):
      raise ValueError("sample_scale must be an integer multiple of 100")
    self._sample_scale = sample_scale
    self._boot_qualifying_power_min_w = config.boot_qualifying_power_min_w
    self._boot_qualifying_seconds_needed = config.boot_qualifying_seconds
    self._boot_qualifying_seconds = 0
    self._last_boot_qualifying_second = None
    self._reference_power_max_w = config.reference_power_max_w
    self._reference_qualify_ms = config.reference_qualify_ms
    self._load_power_min_w = config.load_power_min_w
    self._load_qualify_ms = config.load_qualify_ms
    self._sample_count = config.sample_count
    self._sample_min_interval_ms = config.sample_min_interval_ms
    self._sample_collection_timeout_ms = config.sample_collection_timeout_ms
    self._min_resistance_mohm = config.min_mohm
    self._max_resistance_mohm = config.max_mohm
    self._completed = False
    self._result_mohm = None
    self._samples_mohm = []
    self._reset_count = 0
    # A retry exists only after a clean reference window has actually begun.
    # Rejected riding observations before that are normal, not failed attempts.
    self._attempt_active = False
    self._reset_attempt()

  @property
  def result_mohm(self):
    return self._result_mohm

  @property
  def completed(self):
    return self._completed

  @property
  def phase(self):
    return self._COMPLETE if self._completed else self._phase

  @property
  def boot_qualifying_seconds(self):
    return self._boot_qualifying_seconds

  @property
  def sample_count(self):
    return self._sample_count if self._completed else len(self._samples_mohm)

  @property
  def reference_sample_count(self):
    return min(len(self._reference_samples), self._sample_count)

  @property
  def reset_count(self):
    return self._reset_count

  @property
  def phase_elapsed_seconds(self):
    """Elapsed whole seconds in the active continuous phase, if any."""
    if (self._continuous_started_ms is None or
        self._phase_last_observation_ms is None):
      return 0
    elapsed_ms = time.ticks_diff(
      self._phase_last_observation_ms, self._continuous_started_ms)
    return max(0, elapsed_ms // 1000)

  def _reset_attempt(self):
    # Boot qualification is cumulative. Do not report its normal rejected
    # observations as attempt resets; only count retries after qualification.
    if self._attempt_active:
      self._reset_count += 1
    self._attempt_active = False
    self._reference = None
    self._reference_samples = []
    self._reference_qualify_started_ms = None
    self._reference_last_sample_ms = None
    self._reference_last_sample_second = None
    self._continuous_started_ms = None
    self._phase_last_observation_ms = None
    self._last_continuous_second = None
    self._last_load_sample_second = None
    self._phase = (
      self._BOOT if self._boot_qualifying_seconds <
      self._boot_qualifying_seconds_needed else self._REFERENCE_QUALIFY)
    del self._samples_mohm[:]

  def invalidate(self):
    """Cancel only the current attempt; a later clean attempt remains possible."""
    if not self._completed:
      self._reset_attempt()

  def observe_current(self, current_x100, regen_active=False):
    """Apply current-only failure evidence without advancing time/plateau."""
    if self._completed:
      return
    if (not _is_plain_int(current_x100) or current_x100 < 0 or
        bool(regen_active)):
      self._reset_attempt()
      return

  def _power_at_least(self, voltage_x100, current_x100, power_w):
    return voltage_x100 * current_x100 >= (
      power_w * self._sample_scale * self._sample_scale)

  def _power_below(self, voltage_x100, current_x100, power_w):
    return not self._power_at_least(voltage_x100, current_x100, power_w)

  def _start_continuous_phase(self, now):
    self._continuous_started_ms = now
    self._phase_last_observation_ms = now
    self._last_continuous_second = 0

  def _observe_continuous_second(self, now, qualify_ms):
    elapsed_ms = time.ticks_diff(now, self._continuous_started_ms)
    if elapsed_ms < 0:
      return None
    second = elapsed_ms // 1000
    if second > self._last_continuous_second + 1:
      return None
    if second > self._last_continuous_second:
      self._last_continuous_second = second
    self._phase_last_observation_ms = now
    return elapsed_ms >= qualify_ms

  def expire_observation_gap(self, now):
    """Reset a phase only when it misses an elapsed one-second window."""
    if self._completed:
      return False
    try:
      now = int(now)
    except (TypeError, ValueError, OverflowError):
      self._reset_attempt()
      return True
    if self._phase in (self._REFERENCE_QUALIFY, self._LOAD_QUALIFY):
      if self._continuous_started_ms is None:
        return False
      elapsed_ms = time.ticks_diff(now, self._continuous_started_ms)
      if (elapsed_ms < 0 or elapsed_ms // 1000 >
          self._last_continuous_second + 1):
        self._reset_attempt()
        return True
      return False
    return False

  def _normalize_sample(self, now, voltage_x100, current_x100, boot_ms):
    if not (_is_plain_int(now) and
            _is_plain_int(voltage_x100) and
            _is_plain_int(current_x100) and
            _is_plain_int(boot_ms)):
      return None
    return now, voltage_x100, current_x100, boot_ms

  def _resistance_sample(self, voltage_x100, current_x100):
    reference_voltage_x100 = self._reference[1]
    reference_current_x100 = self._reference[2]
    current_step_x100 = current_x100 - reference_current_x100
    voltage_drop_x100 = reference_voltage_x100 - voltage_x100
    if current_step_x100 <= 0:
      return None
    if voltage_drop_x100 <= 0:
      return None
    resistance_mohm = (1000 * voltage_drop_x100) // current_step_x100
    if not (self._min_resistance_mohm <= resistance_mohm <=
            self._max_resistance_mohm):
      return None
    return resistance_mohm

  def _boot_is_qualified(self, now, voltage_x100, current_x100, boot_ms):
    """Count one qualifying power observation per elapsed boot second."""
    if self._boot_qualifying_seconds >= \
        self._boot_qualifying_seconds_needed:
      return True
    boot_elapsed_ms = time.ticks_diff(now, boot_ms)
    if boot_elapsed_ms < 0:
      return False
    if not self._power_at_least(
        voltage_x100, current_x100, self._boot_qualifying_power_min_w):
      return False
    qualifying_second = boot_elapsed_ms // 1000
    if qualifying_second != self._last_boot_qualifying_second:
      self._last_boot_qualifying_second = qualifying_second
      self._boot_qualifying_seconds += 1
    return self._boot_qualifying_seconds >= \
      self._boot_qualifying_seconds_needed

  def _median(self, values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]

  def _reference_sample(self, now, voltage_x100, current_x100):
    if self._reference_qualify_ms <= 0:
      if (self._reference_last_sample_ms is not None and time.ticks_diff(
          now, self._reference_last_sample_ms) < self._sample_min_interval_ms):
        return False
      self._reference_last_sample_ms = now
      self._reference_samples.append((voltage_x100, current_x100))
      if len(self._reference_samples) > self._sample_count:
        del self._reference_samples[0]
      return True
    second = time.ticks_diff(now, self._continuous_started_ms) // 1000
    if second == self._reference_last_sample_second:
      return False
    self._reference_samples.append((voltage_x100, current_x100))
    if len(self._reference_samples) > self._sample_count:
      del self._reference_samples[0]
    self._reference_last_sample_second = second
    return True

  def _load_sample(self, now, voltage_x100, current_x100):
    second = time.ticks_diff(now, self._continuous_started_ms) // 1000
    if second == self._last_load_sample_second:
      return False
    resistance_mohm = self._resistance_sample(voltage_x100, current_x100)
    if resistance_mohm is None:
      return False
    # Only a usable resistance value consumes this elapsed-second slot.
    self._last_load_sample_second = second
    self._samples_mohm.append(resistance_mohm)
    if len(self._samples_mohm) > self._sample_count:
      del self._samples_mohm[0]
    return True

  def _finish_reference(self, now):
    if len(self._reference_samples) < self._sample_count:
      return False
    self._reference = (
      now,
      self._median([sample[0] for sample in self._reference_samples]),
      self._median([sample[1] for sample in self._reference_samples]),
    )
    self._phase = self._LOAD_QUALIFY
    self._continuous_started_ms = None
    self._phase_last_observation_ms = None
    self._last_continuous_second = None
    self._last_load_sample_second = None
    return True

  def _update_reference(self, now, voltage_x100, current_x100):
    if not self._power_below(
        voltage_x100, current_x100, self._reference_power_max_w):
      self._reset_attempt()
      return None
    if self._reference_qualify_started_ms is None:
      self._reference_qualify_started_ms = now
      self._attempt_active = True
      self._start_continuous_phase(now)
      self._reference_sample(now, voltage_x100, current_x100)
      return None
    if self._reference_qualify_ms <= 0:
      self._reference_sample(now, voltage_x100, current_x100)
      if len(self._reference_samples) >= self._sample_count:
        self._finish_reference(now)
      return None
    complete = self._observe_continuous_second(now, self._reference_qualify_ms)
    if complete is None:
      self._reset_attempt()
      return None
    self._reference_sample(now, voltage_x100, current_x100)
    if complete and not self._finish_reference(now):
      self._reset_attempt()
    return None

  def update(self, now, voltage_x100, current_x100, boot_ms,
             regen_active=False):
    """Consume one new aggregate observation and return the one boot result."""
    if self._completed:
      return None

    sample = self._normalize_sample(now, voltage_x100, current_x100, boot_ms)
    if sample is None:
      self._reset_attempt()
      return None
    now, voltage_x100, current_x100, boot_ms = sample

    if voltage_x100 <= 0 or current_x100 < 0 or bool(regen_active):
      self._reset_attempt()
      return None
    if self._phase == self._BOOT:
      if self._boot_is_qualified(now, voltage_x100, current_x100, boot_ms):
        self._phase = self._REFERENCE_QUALIFY
      return None

    if self._phase == self._REFERENCE_QUALIFY:
      return self._update_reference(now, voltage_x100, current_x100)

    if self._phase == self._LOAD_QUALIFY:
      if self._continuous_started_ms is None:
        if not self._power_at_least(
            voltage_x100, current_x100, self._load_power_min_w):
          return None
        self._start_continuous_phase(now)
        self._load_sample(now, voltage_x100, current_x100)
        return None
      if not self._power_at_least(
          voltage_x100, current_x100, self._load_power_min_w):
        self._reset_attempt()
        return None
      complete = self._observe_continuous_second(now, self._load_qualify_ms)
      if complete is None:
        self._reset_attempt()
        return None
      self._load_sample(now, voltage_x100, current_x100)

      if not complete:
        return None
      if len(self._samples_mohm) < self._sample_count:
        self._reset_attempt()
        return None

      ordered = sorted(self._samples_mohm)
      self._result_mohm = ordered[len(ordered) // 2]
      self._completed = True
      return self._result_mohm


class BatteryResistanceEstimator:
  """Adapter from atomic per-VESC precision samples to the monitor."""

  _PENDING = False
  _INVALID = None

  def __init__(self, config, boot_ms):
    if not _is_plain_int(boot_ms):
      raise ValueError("boot_ms must be an integer")
    self._config = config
    self._boot_ms = boot_ms
    # The LISP data source supplies both values in mV/mA. Keeping the shared
    # scale through the calculation retains its resolution; it cancels from R.
    self._monitor = BatteryResistanceMonitor(config, sample_scale=1000)
    self._last_counters = []

  @property
  def result_mohm(self):
    return self._monitor.result_mohm

  @property
  def completed(self):
    return self._monitor.completed

  @property
  def debug_phase(self):
    return self._monitor.phase

  @property
  def debug_boot_qualifying_seconds(self):
    return self._monitor.boot_qualifying_seconds

  @property
  def debug_sample_count(self):
    return self._monitor.sample_count

  @property
  def debug_reference_sample_count(self):
    return self._monitor.reference_sample_count

  @property
  def debug_error_count(self):
    return self._monitor.reset_count

  @property
  def debug_phase_elapsed_seconds(self):
    return self._monitor.phase_elapsed_seconds

  def _inputs_changed(self, motor_datas):
    count = 0
    changed = False
    try:
      for data in motor_datas:
        counter = data.battery_precision_update_counter
        if not _is_plain_int(counter):
          return None
        if count >= len(self._last_counters):
          self._last_counters.append(counter)
          changed = True
        elif self._last_counters[count] != counter:
          self._last_counters[count] = counter
          changed = True
        count += 1
    except (AttributeError, TypeError):
      return None
    if count == 0:
      return None
    if count != len(self._last_counters):
      del self._last_counters[count:]
      changed = True
    return changed

  def _aggregate_snapshot(self, now, motor_datas):
    total_current_x1000 = 0
    weighted_voltage_numerator = 0
    voltage_sum_x1000 = 0
    voltage_count = 0
    first_timestamp = None
    try:
      for data in motor_datas:
        timestamp = data.battery_precision_last_update_ms
        if not (_is_plain_int(timestamp) and timestamp):
          return self._PENDING

        age_ms = time.ticks_diff(now, timestamp)
        if age_ms < 0:
          return self._INVALID
        if age_ms > self._config.vesc_precision_sample_max_age_ms:
          return self._PENDING
        if (first_timestamp is not None and abs(time.ticks_diff(
            first_timestamp, timestamp)) >
            self._config.dual_vesc_precision_max_skew_ms):
          return self._PENDING
        if first_timestamp is None:
          first_timestamp = timestamp

        voltage_x1000 = data.battery_voltage_measurement_x1000
        current_x1000 = data.battery_current_measurement_x1000
        if not (_is_plain_int(voltage_x1000) and
                _is_plain_int(current_x1000)):
          return self._INVALID
        if current_x1000 < 0 or voltage_x1000 <= 0:
          return self._INVALID
        total_current_x1000 += current_x1000
        weighted_voltage_numerator += voltage_x1000 * current_x1000
        voltage_sum_x1000 += voltage_x1000
        voltage_count += 1
    except (AttributeError, TypeError, ValueError, OverflowError):
      return self._INVALID

    if total_current_x1000 == 0:
      return voltage_sum_x1000 // voltage_count, 0
    weighted_voltage_x1000 = weighted_voltage_numerator // total_current_x1000
    if weighted_voltage_x1000 <= 0:
      return self._INVALID
    return weighted_voltage_x1000, total_current_x1000

  def update(self, now, motor_datas, regen_active=False):
    """Consume changed asynchronous inputs; return the one completed result."""
    if self._monitor.completed:
      return None
    if not _is_plain_int(now):
      self._monitor.invalidate()
      return None
    if bool(regen_active):
      self._monitor.observe_current(0, regen_active=True)
      return None

    inputs_changed = self._inputs_changed(motor_datas)
    if inputs_changed is None:
      self._monitor.invalidate()
      return None
    if not inputs_changed:
      self._monitor.expire_observation_gap(now)
      return None

    sample = self._aggregate_snapshot(now, motor_datas)
    if sample is self._PENDING:
      self._monitor.expire_observation_gap(now)
      return None
    if sample is self._INVALID:
      self._monitor.invalidate()
      return None

    return self._monitor.update(
      now, sample[0], sample[1], self._boot_ms, regen_active=False)
