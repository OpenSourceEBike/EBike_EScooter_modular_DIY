import time


def _is_plain_int(value):
  return isinstance(value, int) and not isinstance(value, bool)


def format_battery_resistance_alert(resistance_mohm):
  return "R {} moh".format(int(resistance_mohm))


def aggregate_battery_measurements(pairs):
  """Combine per-VESC (voltage_x10, current_x10) into one x100 sample."""
  total_current_x10 = 0
  voltage_weight_x10 = 0
  weighted_voltage_numerator = 0
  voltage_sum_x10 = 0
  voltage_count = 0
  try:
    for voltage_x10, current_x10 in pairs:
      if not (_is_plain_int(voltage_x10) and
              _is_plain_int(current_x10)):
        return None
      if voltage_x10 <= 0:
        return None
      total_current_x10 += current_x10
      current_weight_x10 = abs(current_x10)
      voltage_weight_x10 += current_weight_x10
      weighted_voltage_numerator += voltage_x10 * current_weight_x10
      voltage_sum_x10 += voltage_x10
      voltage_count += 1
  except (TypeError, ValueError, OverflowError):
    return None
  if voltage_count == 0:
    return None
  if voltage_weight_x10 == 0:
    return (voltage_sum_x10 // voltage_count) * 10, 0
  weighted_voltage_x10 = weighted_voltage_numerator // voltage_weight_x10
  if weighted_voltage_x10 <= 0:
    return None
  return weighted_voltage_x10 * 10, total_current_x10 * 10


class BatteryResistanceMonitor:
  """One passive result per boot from irregular, validated aggregate samples."""

  _REFERENCE = 0
  _RAMP = 1
  _LOAD = 2
  _COLLECT = 3
  _COMPLETE = 4
  _FAILED = 5

  def __init__(self, config, sample_scale=100):
    if (not _is_plain_int(sample_scale) or sample_scale < 100 or
        sample_scale % 100):
      raise ValueError("sample_scale must be an integer multiple of 100")
    self._sample_scale = sample_scale
    self._reference_power_min_w = config.reference_power_min_w
    self._reference_power_max_w = config.reference_power_max_w
    self._reference_qualify_ms = config.reference_qualify_ms
    self._load_power_min_w = config.load_power_min_w
    self._load_transition_timeout_ms = config.load_transition_timeout_ms
    self._load_qualify_ms = config.load_qualify_ms
    self._sample_collection_timeout_ms = config.sample_collection_timeout_ms
    self._max_attempts = config.max_attempts
    self._sample_count = config.sample_count
    self._min_resistance_mohm = config.min_mohm
    self._max_resistance_mohm = config.max_mohm
    self._completed = False
    self._failed = False
    self._result_mohm = None
    self._samples_mohm = []
    self._reset_count = 0
    self._attempt_count = 0
    self._attempt_active = False
    self._reference_started_ms = None
    self._reference_last_update_ms = None
    self._phase_started_ms = None
    self._collection_started_ms = None
    self._reset_to_reference()

  @property
  def result_mohm(self):
    return self._result_mohm

  @property
  def completed(self):
    return self._completed

  @property
  def failed(self):
    return self._failed

  @property
  def finished(self):
    return self._completed or self._failed

  @property
  def phase(self):
    if self._completed:
      return self._COMPLETE
    if self._failed:
      return self._FAILED
    return self._phase

  @property
  def boot_qualifying_seconds(self):
    # Kept as zero in the existing status packet for wire compatibility.
    return 0

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
    """Elapsed whole seconds in the active phase, if any."""
    if self._phase_started_ms is None:
      return 0
    elapsed_ms = time.ticks_diff(
      self._phase_last_observation_ms or self._phase_started_ms,
      self._phase_started_ms)
    return max(0, elapsed_ms // 1000)

  def _reset_to_reference(self):
    self._attempt_active = False
    self._reference = None
    self._reference_samples = []
    self._reference_started_ms = None
    self._reference_last_update_ms = None
    self._phase_started_ms = None
    self._collection_started_ms = None
    self._continuous_started_ms = None
    self._phase_last_observation_ms = None
    self._last_continuous_second = None
    self._phase = self._REFERENCE
    del self._samples_mohm[:]

  def _fail_attempt(self):
    if not self._attempt_active:
      self._reset_to_reference()
      return
    self._attempt_active = False
    self._reset_count += 1
    if self._attempt_count >= self._max_attempts:
      self._failed = True
      self._phase = self._FAILED
      return
    self._reset_to_reference()

  def invalidate(self):
    """Discard bad input, consuming an attempt only during active load."""
    if self.finished:
      return
    if self._attempt_active:
      self._fail_attempt()
    else:
      self._reset_to_reference()

  def _power_at_least(self, voltage_x100, current_x100, power_w):
    return voltage_x100 * current_x100 >= (
      power_w * self._sample_scale * self._sample_scale)

  def _power_in_reference_window(self, voltage_x100, current_x100):
    power_scaled = voltage_x100 * current_x100
    scale = self._sample_scale * self._sample_scale
    return (self._reference_power_min_w * scale <= power_scaled <=
            self._reference_power_max_w * scale)

  def _start_continuous_phase(self, now):
    self._phase_started_ms = now
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
    """Reset a continuous phase when telemetry stops arriving."""
    if self.finished:
      return False
    try:
      now = int(now)
    except (TypeError, ValueError, OverflowError):
      self.invalidate()
      return True
    if self._phase == self._REFERENCE:
      if (self._reference_started_ms is not None and
          (self._reference_last_update_ms is None or
           time.ticks_diff(now, self._reference_last_update_ms) > 1000)):
        self._reset_to_reference()
        return True
      return False
    if self._phase == self._RAMP and self._attempt_active:
      elapsed_ms = time.ticks_diff(now, self._phase_started_ms)
      if (elapsed_ms < 0 or
          elapsed_ms > self._load_transition_timeout_ms):
        self._fail_attempt()
        return True
      return False
    if self._phase == self._LOAD and self._attempt_active:
      elapsed_ms = time.ticks_diff(now, self._continuous_started_ms)
      if (elapsed_ms < 0 or elapsed_ms // 1000 >
          self._last_continuous_second + 1):
        self._fail_attempt()
        return True
      return False
    if self._phase == self._COLLECT and self._attempt_active:
      elapsed_ms = time.ticks_diff(now, self._collection_started_ms)
      if (elapsed_ms < 0 or
          elapsed_ms > self._sample_collection_timeout_ms):
        self._fail_attempt()
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

  def _trimmed_mean(self, values):
    ordered = sorted(values)
    middle = ordered[1:-1]
    return sum(middle) // len(middle)

  def _reference_sample(self, voltage_x100, current_x100):
    self._reference_samples.append((voltage_x100, current_x100))
    if len(self._reference_samples) > self._sample_count:
      del self._reference_samples[0]
    return True

  def _load_sample(self, voltage_x100, current_x100):
    resistance_mohm = self._resistance_sample(voltage_x100, current_x100)
    if resistance_mohm is None:
      return False
    self._samples_mohm.append(resistance_mohm)
    if len(self._samples_mohm) > self._sample_count:
      del self._samples_mohm[0]
    return True

  def _finish_reference(self, now):
    if (self._reference_started_ms is None or
        time.ticks_diff(now, self._reference_started_ms) <
        self._reference_qualify_ms or
        len(self._reference_samples) < self._sample_count):
      return False
    self._reference = (
      now,
      self._trimmed_mean(
        [sample[0] for sample in self._reference_samples]),
      self._trimmed_mean(
        [sample[1] for sample in self._reference_samples]),
    )
    self._phase = self._RAMP
    self._phase_started_ms = None
    self._continuous_started_ms = None
    self._phase_last_observation_ms = None
    self._last_continuous_second = None
    return True

  def _update_reference(self, now, voltage_x100, current_x100):
    if not self._power_in_reference_window(voltage_x100, current_x100):
      self._reset_to_reference()
      return False
    if self._reference_started_ms is None:
      self._reference_started_ms = now
      self._phase_started_ms = now
    self._reference_last_update_ms = now
    # The reference phase is continuous too: keep the progress timestamp
    # moving on every valid neutral-power observation so the debug/status
    # counter reflects the actual ten-second window.
    self._phase_last_observation_ms = now
    self._reference_sample(voltage_x100, current_x100)
    return self._finish_reference(now)

  def _start_ramp(self, now):
    self._attempt_count += 1
    self._attempt_active = True
    self._phase = self._RAMP
    self._phase_started_ms = now

  def _start_load(self, now, voltage_x100, current_x100):
    self._phase = self._LOAD
    self._phase_started_ms = now
    self._start_continuous_phase(now)
    self._load_sample(voltage_x100, current_x100)

  def _start_collection(self, now, voltage_x100, current_x100):
    self._phase = self._COLLECT
    self._phase_started_ms = now
    self._phase_last_observation_ms = now
    self._collection_started_ms = now
    self._samples_mohm = []
    self._load_sample(voltage_x100, current_x100)

  def update(self, now, voltage_x100, current_x100, boot_ms,
             regen_active=False):
    """Consume one new aggregate observation and return the one boot result."""
    if self.finished:
      return None

    sample = self._normalize_sample(now, voltage_x100, current_x100, boot_ms)
    if sample is None:
      self.invalidate()
      return None
    now, voltage_x100, current_x100, boot_ms = sample

    if voltage_x100 <= 0:
      self.invalidate()
      return None

    if self._phase == self._REFERENCE:
      self._update_reference(now, voltage_x100, current_x100)
      return None

    if self._phase == self._RAMP:
      power_scaled = voltage_x100 * current_x100
      reference_min_scaled = (
        self._reference_power_min_w * self._sample_scale *
        self._sample_scale)
      reference_max_scaled = (
        self._reference_power_max_w * self._sample_scale *
        self._sample_scale)
      # A validated reference is held while waiting for the rider to apply
      # load. Neutral power here is not a failed attempt and must not restart
      # the ten-second reference window.
      if not self._attempt_active and reference_min_scaled <= power_scaled <= \
          reference_max_scaled:
        self._phase_last_observation_ms = now
        return None
      if not self._attempt_active and power_scaled < reference_min_scaled:
        self._reset_to_reference()
        return None
      if self._phase_started_ms is None:
        self._start_ramp(now)
      ramp_elapsed_ms = time.ticks_diff(now, self._phase_started_ms)
      if ramp_elapsed_ms < 0 or ramp_elapsed_ms > \
          self._load_transition_timeout_ms:
        self._fail_attempt()
        return None
      if self._power_at_least(
          voltage_x100, current_x100, self._load_power_min_w):
        self._start_load(now, voltage_x100, current_x100)
      elif power_scaled > reference_max_scaled:
        # Still above +100 W: keep waiting inside the three-second ramp.
        return None
      else:
        self._fail_attempt()
      return None

    if self._phase == self._LOAD:
      if not self._power_at_least(
          voltage_x100, current_x100, self._load_power_min_w):
        self._fail_attempt()
        return None
      complete = self._observe_continuous_second(now, self._load_qualify_ms)
      if complete is None:
        self._fail_attempt()
        return None
      if complete:
        self._start_collection(now, voltage_x100, current_x100)
      return None

    if self._phase == self._COLLECT:
      if not self._power_at_least(
          voltage_x100, current_x100, self._load_power_min_w):
        self._fail_attempt()
        return None
      collection_elapsed_ms = time.ticks_diff(
        now, self._collection_started_ms)
      if collection_elapsed_ms < 0 or collection_elapsed_ms > \
          self._sample_collection_timeout_ms:
        self._fail_attempt()
        return None
      self._load_sample(voltage_x100, current_x100)
      self._phase_last_observation_ms = now
      if len(self._samples_mohm) < self._sample_count:
        return None
      self._result_mohm = self._trimmed_mean(self._samples_mohm)
      self._completed = True
      self._phase = self._COMPLETE
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
  def finished(self):
    return self._monitor.finished

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
    voltage_weight_x1000 = 0
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
        if voltage_x1000 <= 0:
          return self._INVALID
        total_current_x1000 += current_x1000
        current_weight_x1000 = abs(current_x1000)
        voltage_weight_x1000 += current_weight_x1000
        weighted_voltage_numerator += voltage_x1000 * current_weight_x1000
        voltage_sum_x1000 += voltage_x1000
        voltage_count += 1
    except (AttributeError, TypeError, ValueError, OverflowError):
      return self._INVALID

    if voltage_count == 0:
      return self._INVALID
    if voltage_weight_x1000 == 0:
      return voltage_sum_x1000 // voltage_count, 0
    weighted_voltage_x1000 = \
      weighted_voltage_numerator // voltage_weight_x1000
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
      now, sample[0], sample[1], self._boot_ms, regen_active=regen_active)
