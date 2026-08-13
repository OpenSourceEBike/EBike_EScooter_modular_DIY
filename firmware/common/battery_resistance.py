import time


def _is_plain_int(value):
  return isinstance(value, int) and not isinstance(value, bool)


def aggregate_battery_measurements(pairs):
  """Combine per-VESC (voltage_x10, current_x10) into one x100 sample."""
  total_current_x10 = 0
  weighted_voltage_numerator = 0
  try:
    for voltage_x10, current_x10 in pairs:
      if not (_is_plain_int(voltage_x10) and
              _is_plain_int(current_x10)):
        return None
      if current_x10 < 0:
        return None
      if current_x10 and voltage_x10 <= 0:
        return None
      total_current_x10 += current_x10
      weighted_voltage_numerator += voltage_x10 * current_x10
  except (TypeError, ValueError, OverflowError):
    return None
  if total_current_x10 <= 0:
    return None
  weighted_voltage_x10 = weighted_voltage_numerator // total_current_x10
  if weighted_voltage_x10 <= 0:
    return None
  return weighted_voltage_x10 * 10, total_current_x10 * 10


class BatteryResistanceMonitor:
  """One passive result per boot from irregular, validated aggregate samples."""

  def __init__(self, config):
    self._boot_delay_ms = config.boot_delay_ms
    self._reference_current_min_x100 = config.reference_current_min_a_x100
    self._load_current_min_x100 = config.load_current_min_a_x100
    self._min_current_step_x100 = config.min_current_step_a_x100
    self._load_current_stability_x100 = config.load_current_stability_a_x100
    self._load_qualify_ms = config.load_qualify_ms
    self._sample_count = config.sample_count
    self._sample_min_interval_ms = config.sample_min_interval_ms
    self._sample_collection_timeout_ms = config.sample_collection_timeout_ms
    self._reference_max_age_ms = config.reference_max_age_ms
    self._max_sample_gap_ms = config.motor_sample_gap_ms
    self._min_resistance_mohm = config.min_mohm
    self._max_resistance_mohm = config.max_mohm
    self._completed = False
    self._result_mohm = None
    self._samples_mohm = []
    self._reset_attempt()

  @property
  def result_mohm(self):
    return self._result_mohm

  @property
  def completed(self):
    return self._completed

  def _reset_attempt(self):
    self._reference = None
    self._load_started_ms = None
    self._load_current_x100 = 0
    self._last_observation_ms = None
    self._last_accepted_sample_ms = None
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
    if self._load_started_ms is not None and (
        current_x100 < self._load_current_min_x100 or
        abs(current_x100 - self._load_current_x100) >
          self._load_current_stability_x100):
      self._reset_attempt()

  def expire_observation_gap(self, now):
    """Reset an active load attempt only after its configured input gap."""
    if self._completed or self._last_observation_ms is None:
      return False
    try:
      gap_ms = time.ticks_diff(int(now), self._last_observation_ms)
    except (TypeError, ValueError, OverflowError):
      self._reset_attempt()
      return True
    if gap_ms > self._max_sample_gap_ms:
      self._reset_attempt()
      return True
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
    if current_step_x100 < self._min_current_step_x100:
      return None
    if voltage_drop_x100 <= 0:
      return None
    resistance_mohm = (1000 * voltage_drop_x100) // current_step_x100
    if not (self._min_resistance_mohm <= resistance_mohm <=
            self._max_resistance_mohm):
      return None
    return resistance_mohm

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
    if time.ticks_diff(now, boot_ms) < self._boot_delay_ms:
      self._reset_attempt()
      return None

    if self._load_started_ms is None:
      if (self._reference_current_min_x100 < current_x100 <
          self._load_current_min_x100):
        self._reference = (now, voltage_x100, current_x100)
        return None
      if current_x100 < self._load_current_min_x100:
        return None
      if self._reference is None:
        return None

      reference_age_ms = time.ticks_diff(now, self._reference[0])
      current_step_x100 = current_x100 - self._reference[2]
      if (reference_age_ms < 0 or
          reference_age_ms > self._reference_max_age_ms or
          current_step_x100 < self._min_current_step_x100):
        self._reset_attempt()
        return None

      self._load_started_ms = now
      self._load_current_x100 = current_x100
      self._last_observation_ms = now
      return None

    observation_gap_ms = time.ticks_diff(now, self._last_observation_ms)
    if (observation_gap_ms <= 0 or
        observation_gap_ms > self._max_sample_gap_ms or
        current_x100 < self._load_current_min_x100 or
        abs(current_x100 - self._load_current_x100) >
          self._load_current_stability_x100):
      self._reset_attempt()
      return None
    self._last_observation_ms = now

    elapsed_ms = time.ticks_diff(now, self._load_started_ms)
    if elapsed_ms < self._load_qualify_ms:
      return None
    if elapsed_ms > (
        self._load_qualify_ms + self._sample_collection_timeout_ms):
      self._reset_attempt()
      return None

    if self._last_accepted_sample_ms is not None and time.ticks_diff(
        now, self._last_accepted_sample_ms) < self._sample_min_interval_ms:
      return None

    resistance_mohm = self._resistance_sample(voltage_x100, current_x100)
    if resistance_mohm is None:
      # A single noisy calculated point does not destroy an otherwise valid
      # load window. Continue looking until the collection deadline.
      return None

    self._samples_mohm.append(resistance_mohm)
    self._last_accepted_sample_ms = now
    if len(self._samples_mohm) < self._sample_count:
      return None

    ordered = sorted(self._samples_mohm)
    self._result_mohm = ordered[len(ordered) // 2]
    self._completed = True
    self._reset_attempt()
    return self._result_mohm


class BatteryResistanceEstimator:
  """Feature-local adapter from asynchronous per-VESC fields to the monitor."""

  _PENDING = False
  _INVALID = None

  def __init__(self, config, boot_ms):
    if not _is_plain_int(boot_ms):
      raise ValueError("boot_ms must be an integer")
    self._config = config
    self._boot_ms = boot_ms
    self._monitor = BatteryResistanceMonitor(config)
    self._last_counters = []
    self._last_current_timestamps = []

  @property
  def result_mohm(self):
    return self._monitor.result_mohm

  @property
  def completed(self):
    return self._monitor.completed

  def _inputs_changed(self, motor_datas):
    count = 0
    changed = False
    try:
      for data in motor_datas:
        counter = data.battery_pair_update_counter
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

  def _current_observation(self, now, motor_datas):
    count = 0
    first_timestamp = None
    timestamps_changed = False
    total_current_x10 = 0
    try:
      for data in motor_datas:
        timestamp = data.status_4_last_update_ms
        current_x10 = data.battery_current_measurement_x10
        if not (_is_plain_int(timestamp) and timestamp):
          return self._PENDING, None, False
        if not _is_plain_int(current_x10):
          return self._INVALID, None, False
        age_ms = time.ticks_diff(now, timestamp)
        if age_ms < 0:
          return self._INVALID, None, False
        if age_ms > self._config.vesc_signal_max_age_ms:
          return self._PENDING, None, False
        if current_x10 < 0:
          return self._INVALID, None, False
        if (first_timestamp is not None and abs(time.ticks_diff(
            first_timestamp, timestamp)) >
            self._config.dual_vesc_max_skew_ms):
          return self._PENDING, None, False
        if first_timestamp is None:
          first_timestamp = timestamp
        if count >= len(self._last_current_timestamps):
          self._last_current_timestamps.append(timestamp)
          timestamps_changed = True
        elif self._last_current_timestamps[count] != timestamp:
          self._last_current_timestamps[count] = timestamp
          timestamps_changed = True
        count += 1
        total_current_x10 += current_x10
    except (AttributeError, TypeError, ValueError, OverflowError):
      return self._INVALID, None, False
    if count != len(self._last_current_timestamps):
      del self._last_current_timestamps[count:]
      timestamps_changed = True
    return True, total_current_x10 * 10, timestamps_changed

  def _aggregate_snapshot(self, now, motor_datas):
    total_current_x10 = 0
    weighted_voltage_numerator = 0
    first_current_timestamp = None
    first_voltage_timestamp = None
    try:
      for data in motor_datas:
        current_timestamp = data.status_4_last_update_ms
        voltage_timestamp = data.status_5_last_update_ms
        if not (_is_plain_int(current_timestamp) and current_timestamp and
                _is_plain_int(voltage_timestamp) and voltage_timestamp):
          return self._PENDING

        current_age_ms = time.ticks_diff(now, current_timestamp)
        voltage_age_ms = time.ticks_diff(now, voltage_timestamp)
        if current_age_ms < 0 or voltage_age_ms < 0:
          return self._INVALID
        if (current_age_ms > self._config.vesc_signal_max_age_ms or
            voltage_age_ms > self._config.vesc_signal_max_age_ms):
          return self._PENDING
        if abs(time.ticks_diff(
            current_timestamp, voltage_timestamp)) > \
            self._config.vesc_voltage_current_max_skew_ms:
          return self._PENDING

        if first_current_timestamp is not None and (
            abs(time.ticks_diff(
              first_current_timestamp, current_timestamp)) >
              self._config.dual_vesc_max_skew_ms or
            abs(time.ticks_diff(
              first_voltage_timestamp, voltage_timestamp)) >
              self._config.dual_vesc_max_skew_ms):
          return self._PENDING
        if first_current_timestamp is None:
          first_current_timestamp = current_timestamp
          first_voltage_timestamp = voltage_timestamp

        voltage_x10 = data.battery_voltage_measurement_x10
        current_x10 = data.battery_current_measurement_x10
        if not (_is_plain_int(voltage_x10) and _is_plain_int(current_x10)):
          return self._INVALID
        if current_x10 < 0 or (current_x10 and voltage_x10 <= 0):
          return self._INVALID
        total_current_x10 += current_x10
        weighted_voltage_numerator += voltage_x10 * current_x10
    except (AttributeError, TypeError, ValueError, OverflowError):
      return self._INVALID

    if total_current_x10 <= 0:
      return self._INVALID
    weighted_voltage_x10 = weighted_voltage_numerator // total_current_x10
    if weighted_voltage_x10 <= 0:
      return self._INVALID
    return weighted_voltage_x10 * 10, total_current_x10 * 10

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

    current_state, total_current_x100, current_changed = \
      self._current_observation(now, motor_datas)
    if current_state is self._INVALID:
      self._monitor.invalidate()
      return None
    if current_state is True and current_changed:
      self._monitor.observe_current(total_current_x100)

    sample = self._aggregate_snapshot(now, motor_datas)
    if sample is self._PENDING:
      self._monitor.expire_observation_gap(now)
      return None
    if sample is self._INVALID:
      self._monitor.invalidate()
      return None

    return self._monitor.update(
      now, sample[0], sample[1], self._boot_ms, regen_active=False)
