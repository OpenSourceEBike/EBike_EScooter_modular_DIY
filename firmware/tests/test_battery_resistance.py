import os
import importlib.util
import tempfile
import time
import unittest
from types import SimpleNamespace


if not hasattr(time, "ticks_diff"):
  time.ticks_diff = lambda newer, older: newer - older

from common.battery_resistance import (
  BatteryResistanceEstimator,
  BatteryResistanceMonitor,
  aggregate_battery_measurements,
  format_battery_resistance_alert,
)
from common.config_battery_resistance import (
  BatteryResistanceConfig,
  validate_battery_resistance_display_config,
  validate_battery_resistance_measurement_config,
)
from common.battery_resistance_persistence import (
  load_battery_resistance_history,
  save_battery_resistance_history,
)


class BatteryResistanceMonitorTests(unittest.TestCase):
  def make_config(self):
    config = BatteryResistanceConfig()
    config.reference_qualify_ms = 1000
    config.load_qualify_ms = 4000
    return config

  def collect_reference(self, monitor, start_ms=0, voltage_x100=5400,
                        current_x100=0):
    for index in range(11):
      monitor.update(
        start_ms + (index * 100), voltage_x100, current_x100, 0)
    return start_ms + 1000

  def start_load(self, monitor, start_ms=0):
    trigger_ms = self.collect_reference(monitor, start_ms)
    monitor.update(trigger_ms + 100, 5400, 500, 0)
    load_start = trigger_ms + 200
    monitor.update(load_start, 5300, 1600, 0)
    return load_start

  def test_starts_in_reference_and_keeps_latest_five_samples(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    for index in range(11):
      monitor.update(index * 100, 5300 + (index * 10), 0, 0)
    self.assertEqual(monitor.phase, 1)
    self.assertEqual(monitor.reference_sample_count, 5)

    monitor.update(1100, 5400, 500, 0)
    self.assertEqual(monitor.phase, 1)
    self.assertEqual(monitor._reference[1], 5380)

  def test_exactly_100_w_freezes_reference(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.collect_reference(monitor)
    self.assertEqual(monitor.phase, 1)

  def test_valid_reference_waits_at_zero_power_without_retrying(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    reference_end = self.collect_reference(monitor)
    for timestamp in (reference_end + 100, reference_end + 1000,
                      reference_end + 2000):
      monitor.update(timestamp, 5400, 0, 0)
    self.assertEqual(monitor.phase, 1)
    self.assertEqual(monitor.reset_count, 0)
    self.assertEqual(monitor._attempt_count, 0)

  def test_reference_phase_elapsed_seconds_tracks_neutral_observations(self):
    config = self.make_config()
    config.reference_qualify_ms = 2000
    monitor = BatteryResistanceMonitor(config)
    monitor.update(0, 5400, 0, 0)
    monitor.update(500, 5400, 0, 0)
    self.assertEqual(monitor.phase_elapsed_seconds, 0)
    monitor.update(1000, 5400, 0, 0)
    self.assertEqual(monitor.phase_elapsed_seconds, 1)

  def test_reference_does_not_freeze_until_five_samples_exist(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    for timestamp in (0, 100, 200, 300, 400):
      monitor.update(timestamp, 5400, 0, 0)
    monitor.update(500, 5400, 500, 0)
    self.assertEqual(monitor.phase, 0)
    self.assertEqual(monitor.reference_sample_count, 0)
    self.assertEqual(monitor.reset_count, 0)

  def test_waiting_between_100_and_750_w_does_not_start_attempt(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    trigger_ms = self.collect_reference(monitor)
    monitor.update(trigger_ms + 100, 5400, 500, 0)
    monitor.update(trigger_ms + 500, 5300, 500, 0)
    self.assertEqual(monitor.phase, 1)
    self.assertEqual(monitor.phase_elapsed_seconds, 0)
    self.assertEqual(monitor.reset_count, 0)

  def test_load_completes_after_continuous_window(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    result = None
    for offset in (1000, 2000, 3000, 4000, 4100, 4200, 4300, 4400):
      result = monitor.update(start_ms + offset, 5300, 1600, 0)
    self.assertEqual(result, 62)
    self.assertTrue(monitor.completed)
    self.assertEqual(monitor.phase, 4)

  def test_load_uses_trimmed_mean_of_five_samples(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    for offset in (1000, 2000, 3000, 4000):
      monitor.update(start_ms + offset, 5300, 1600, 0)
    result = None
    for offset, voltage in zip((4100, 4200, 4300, 4400),
                               (5336, 5304, 5272, 5240)):
      result = monitor.update(start_ms + offset, voltage, 1600, 0)
    self.assertEqual(result, 67)

  def test_reference_uses_trimmed_mean_of_five_samples(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    for timestamp, voltage in zip(
        range(0, 1100, 100),
        (5300, 5400, 5500, 5600, 5700, 5300, 5400, 5500, 5600, 5700, 5500)):
      monitor.update(timestamp, voltage, 0, 0)
    self.assertEqual(monitor._reference[1:], (5533, 0))

  def test_power_drop_consumes_one_attempt_and_restarts_reference(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    monitor.update(start_ms + 1000, 5300, 1400, 0)
    self.assertEqual(monitor.phase, 0)
    self.assertEqual(monitor.reset_count, 1)
    self.assertEqual(monitor.reference_sample_count, 0)

  def test_retry_can_complete_after_a_failed_attempt(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    monitor.update(start_ms + 1000, 5300, 1400, 0)

    start_ms = self.start_load(monitor, start_ms + 2000)
    result = None
    for offset in (1000, 2000, 3000, 4000, 4100, 4200, 4300, 4400):
      result = monitor.update(start_ms + offset, 5300, 1600, 0)
    self.assertEqual(result, 62)
    self.assertEqual(monitor.reset_count, 1)
    self.assertTrue(monitor.completed)

  def test_consecutive_valid_resistance_samples_are_accepted(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    for offset in (1000, 2000, 3000, 4000):
      monitor.update(start_ms + offset, 5300, 1600, 0)
    monitor.update(start_ms + 4100, 5300, 1600, 0)
    self.assertEqual(monitor.sample_count, 2)
    monitor.update(start_ms + 4200, 5300, 1600, 0)
    self.assertEqual(monitor.sample_count, 3)

  def test_observation_gap_consumes_one_attempt(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    start_ms = self.start_load(monitor)
    self.assertTrue(monitor.expire_observation_gap(start_ms + 2001))
    self.assertEqual(monitor.phase, 0)
    self.assertEqual(monitor.reset_count, 1)

  def test_twenty_fifth_failed_attempt_is_terminal(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    now = 0
    for attempt in range(25):
      start_ms = self.start_load(monitor, now)
      monitor.update(start_ms + 1000, 5300, 1400, 0)
      now = start_ms + 2000
      self.assertEqual(monitor.reset_count, attempt + 1)
    self.assertTrue(monitor.failed)
    self.assertTrue(monitor.finished)
    self.assertFalse(monitor.completed)
    self.assertEqual(monitor.phase, 5)

  def test_twenty_fifth_attempt_can_still_succeed(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    now = 0
    for _ in range(24):
      start_ms = self.start_load(monitor, now)
      monitor.update(start_ms + 1000, 5300, 1400, 0)
      now = start_ms + 2000

    start_ms = self.start_load(monitor, now)
    result = None
    for offset in (1000, 2000, 3000, 4000, 4100, 4200, 4300, 4400):
      result = monitor.update(start_ms + offset, 5300, 1600, 0)
    self.assertEqual(result, 62)
    self.assertEqual(monitor.reset_count, 24)
    self.assertTrue(monitor.completed)
    self.assertFalse(monitor.failed)

  def test_invalid_input_before_load_does_not_consume_attempt(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    monitor.update(0, 5400.0, 100, 0)
    self.assertEqual(monitor.reset_count, 0)
    self.assertEqual(monitor.phase, 0)

  def test_default_configuration_matches_measurement_contract(self):
    config = BatteryResistanceConfig()
    self.assertEqual(config.reference_power_min_w, -100)
    self.assertEqual(config.reference_power_max_w, 100)
    self.assertEqual(config.load_power_min_w, 750)
    self.assertEqual(config.reference_qualify_ms, 10000)
    self.assertEqual(config.load_transition_timeout_ms, 3000)
    self.assertEqual(config.load_qualify_ms, 15000)
    self.assertEqual(config.max_attempts, 25)

  def test_default_load_starts_at_exactly_750_w_and_runs_fifteen_seconds(self):
    monitor = BatteryResistanceMonitor(BatteryResistanceConfig())
    for timestamp_ms in range(0, 10001, 1000):
      monitor.update(timestamp_ms, 5400, 0, 0)
    monitor.update(10100, 5400, 500, 0)
    monitor.update(10200, 5000, 1500, 0)
    for timestamp_ms in range(11200, 25200, 1000):
      self.assertIsNone(monitor.update(timestamp_ms, 5000, 1500, 0))
    monitor.update(25200, 5000, 1500, 0)
    self.assertEqual(monitor.phase, 3)

  def test_aggregate_combines_dual_motor_values(self):
    self.assertEqual(
      aggregate_battery_measurements(((540, 100), (530, 200))),
      (5330, 3000),
    )
    self.assertEqual(
      aggregate_battery_measurements(((540, 0), (530, 0))),
      (5350, 0),
    )
    self.assertEqual(
      aggregate_battery_measurements(((540, -100), (530, -200))),
      (5330, -3000),
    )

  def test_mixed_sign_currents_keep_voltage_between_branch_voltages(self):
    self.assertEqual(
      aggregate_battery_measurements(((540, 100), (539, -90))),
      (5390, 100),
    )

  def test_malformed_aggregate_input_is_rejected(self):
    self.assertIsNone(
      aggregate_battery_measurements(((540, 0), (0, 0))))
    self.assertIsNone(
      aggregate_battery_measurements(((540.0, 100), (530, 200))))
    self.assertIsNone(
      aggregate_battery_measurements(((540, 100), (530, None))))


class FakeMotorData:
  def __init__(self):
    self.battery_precision_update_counter = 0
    self.battery_precision_last_update_ms = 0
    self.battery_current_measurement_x1000 = None
    self.battery_voltage_measurement_x1000 = None

  def precision(self, timestamp_ms, voltage_x1000, current_x1000):
    self.battery_precision_last_update_ms = timestamp_ms
    self.battery_voltage_measurement_x1000 = voltage_x1000
    self.battery_current_measurement_x1000 = current_x1000
    self.battery_precision_update_counter += 1


class BatteryResistanceEstimatorTests(unittest.TestCase):
  def make_estimator(self):
    config = BatteryResistanceConfig()
    config.reference_qualify_ms = 1000
    config.load_qualify_ms = 4000
    return BatteryResistanceEstimator(config, 0)

  def precision_sample(self, estimator, data, timestamp_ms,
                       current_x1000, voltage_x1000):
    data.precision(timestamp_ms, voltage_x1000, current_x1000)
    return estimator.update(timestamp_ms, (data,))

  def start_attempt(self, estimator, data, start_ms=100):
    for offset in range(0, 1100, 100):
      self.precision_sample(
        estimator, data, start_ms + offset, 0, 54000)
    self.precision_sample(estimator, data, start_ms + 1100, 5000, 54000)
    return self.precision_sample(
      estimator, data, start_ms + 1200, 16000, 53000)

  def dual_precision_sample(self, estimator, rear, front, timestamp_ms,
                            rear_current_x1000, front_current_x1000,
                            rear_voltage_x1000, front_voltage_x1000):
    rear.precision(
      timestamp_ms, rear_voltage_x1000, rear_current_x1000)
    estimator.update(timestamp_ms, (rear, front))
    front.precision(
      timestamp_ms + 20, front_voltage_x1000, front_current_x1000)
    return estimator.update(timestamp_ms + 20, (rear, front))

  def test_atomic_precision_samples_complete_attempt(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.start_attempt(estimator, data)
    result = None
    for timestamp_ms in range(2200, 6201, 1000):
      result = self.precision_sample(
        estimator, data, timestamp_ms, 16000, 53000)
    for timestamp_ms in (6300, 6400, 6500, 6600):
      result = self.precision_sample(estimator, data, timestamp_ms, 16000, 53000)
    self.assertEqual(result, 62)
    self.assertTrue(estimator.completed)

  def test_unchanged_input_gap_fails_active_attempt(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.start_attempt(estimator, data)
    estimator.update(3601, (data,))
    self.assertEqual(estimator.debug_error_count, 1)
    self.assertEqual(estimator.debug_phase, 0)

  def test_zero_current_reference_is_accepted(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    for timestamp_ms in range(100, 1101, 100):
      self.precision_sample(estimator, data, timestamp_ms, 0, 54000)
    self.precision_sample(estimator, data, 1200, 5000, 54000)
    self.precision_sample(estimator, data, 1300, 16000, 53000)
    result = None
    for timestamp_ms in (2400, 3400, 4400, 5400):
      result = self.precision_sample(
        estimator, data, timestamp_ms, 16000, 53000)
    for timestamp_ms in (5500, 5600, 5700, 5800):
      result = self.precision_sample(estimator, data, timestamp_ms, 16000, 53000)
    self.assertEqual(result, 62)

  def test_dual_vesc_async_samples_complete_measurement(self):
    estimator = self.make_estimator()
    rear = FakeMotorData()
    front = FakeMotorData()
    for timestamp_ms in range(100, 1101, 100):
      self.dual_precision_sample(
        estimator, rear, front, timestamp_ms,
        0, 0, 54000, 53900)
    self.dual_precision_sample(
      estimator, rear, front, 1200,
      5000, 5000, 54000, 54000)
    self.dual_precision_sample(
      estimator, rear, front, 1300,
      16000, 16000, 53000, 53000)

    result = None
    for timestamp_ms in (2300, 3300, 4300, 5300, 5400, 5500, 5600, 5700):
      result = self.dual_precision_sample(
        estimator, rear, front, timestamp_ms,
        16000, 16000, 53000, 53000)
    self.assertEqual(estimator.result_mohm, 29)
    self.assertTrue(estimator.completed)

  def test_front_voltage_and_current_are_required(self):
    estimator = self.make_estimator()
    rear = FakeMotorData()
    front = FakeMotorData()
    rear.precision(100, 54000, 0)
    front.precision(120, None, 0)
    estimator.update(120, (rear, front))
    self.assertEqual(estimator.debug_reference_sample_count, 0)

    front.precision(220, 54000, 0)
    estimator.update(220, (rear, front))
    self.assertEqual(estimator.debug_reference_sample_count, 1)
    self.assertEqual(estimator.debug_error_count, 0)

  def test_dual_vesc_excessive_skew_remains_pending(self):
    estimator = self.make_estimator()
    rear = FakeMotorData()
    front = FakeMotorData()
    rear.precision(100, 54000, 0)
    front.precision(400, 54000, 1000)
    estimator.update(400, (rear, front))
    self.assertEqual(estimator.debug_phase, 0)
    self.assertEqual(estimator.debug_reference_sample_count, 0)
    self.assertEqual(estimator.debug_error_count, 0)


class BatteryResistanceConfigTests(unittest.TestCase):
  def test_production_config_requires_five_samples(self):
    config = BatteryResistanceConfig()
    self.assertIsNone(
      validate_battery_resistance_measurement_config(config))
    config.sample_count = 3
    self.assertEqual(
      validate_battery_resistance_measurement_config(config),
      "sample_count must be 5",
    )

  def test_non_integer_measurement_value_is_rejected(self):
    config = BatteryResistanceConfig()
    config.max_attempts = float("nan")
    self.assertIsNotNone(
      validate_battery_resistance_measurement_config(config))

  def test_measurement_timing_and_attempt_count_are_fixed(self):
    config = BatteryResistanceConfig()
    config.load_qualify_ms = 19999
    self.assertEqual(
      validate_battery_resistance_measurement_config(config),
      "load_qualify_ms must be 15000",
    )
    config.load_qualify_ms = 15000
    config.max_attempts = 24
    self.assertEqual(
      validate_battery_resistance_measurement_config(config),
      "max_attempts must be 25",
    )

  def test_dual_vesc_skew_cannot_exceed_source_age(self):
    config = BatteryResistanceConfig()
    config.dual_vesc_precision_max_skew_ms = \
      config.vesc_precision_sample_max_age_ms + 1
    self.assertIsNotNone(
      validate_battery_resistance_measurement_config(config))

  def test_generated_temp_path_collision_is_rejected(self):
    config = BatteryResistanceConfig()
    config.summary_file_path = "resistance.csv"
    config.history_file_path = "resistance.csv.tmp"
    self.assertIsNotNone(validate_battery_resistance_display_config(config))


class BatteryResistanceAlertLayoutTests(unittest.TestCase):
  def load_font(self, filename):
    path = os.path.join(
      os.path.dirname(os.path.dirname(__file__)),
      '02_diy_display', 'fonts', filename,
    )
    spec = importlib.util.spec_from_file_location(filename, path)
    font = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(font)
    return font

  def text_width(self, font, text):
    return sum(font.get_ch(character)[2] for character in text)

  def test_alert_uses_requested_compact_text_and_fits_main_screen(self):
    text = format_battery_resistance_alert(2500)
    self.assertEqual(text, 'R 2500 moh')
    self.assertLessEqual(self.text_width(
      self.load_font('robotobold12.py'), text), 78)


class BatteryResistancePersistenceTests(unittest.TestCase):
  def setUp(self):
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.config = BatteryResistanceConfig()
    self.config.summary_file_path = os.path.join(
      self.temporary_directory.name, 'summary.csv')
    self.config.history_file_path = os.path.join(
      self.temporary_directory.name, 'history.csv')

  def tearDown(self):
    self.temporary_directory.cleanup()

  def state(self, last=83, minimum=71, maximum=109, dirty=False):
    return SimpleNamespace(
      battery_resistance_last_mohm=last,
      battery_resistance_last_timestamp=1000,
      battery_resistance_min_mohm=minimum,
      battery_resistance_min_timestamp=900,
      battery_resistance_max_mohm=maximum,
      battery_resistance_max_timestamp=800,
      battery_resistance_history_dirty=dirty,
      battery_resistance_history_row_saved=False,
      battery_resistance_summary_repair_pending=False,
    )

  def save_summary_only(self, state):
    state.battery_resistance_summary_repair_pending = True
    self.assertTrue(save_battery_resistance_history(state, self.config))

  def test_tmp_is_loadable_if_power_fails_after_primary_is_removed(self):
    old = self.state(last=80, minimum=70, maximum=100)
    self.save_summary_only(old)
    os.remove(self.config.summary_file_path)
    lines = (
      'kind,resistance_mohm,timestamp\n',
      'last,84,na\n', 'min,70,na\n', 'max,100,na\n',
    )
    with open(self.config.summary_file_path + '.tmp', 'w') as temporary:
      temporary.writelines(lines)
    loaded = self.state(last=None, minimum=None, maximum=None)
    self.assertTrue(load_battery_resistance_history(loaded, self.config))
    self.assertEqual(loaded.battery_resistance_last_mohm, 84)
    self.assertTrue(loaded.battery_resistance_summary_repair_pending)

  def test_history_failure_does_not_publish_new_summary(self):
    old = self.state(last=80, minimum=70, maximum=100)
    self.save_summary_only(old)
    with open(self.config.summary_file_path, 'r') as summary:
      original_summary = summary.read()
    new = self.state(last=84, minimum=70, maximum=100, dirty=True)
    self.config.history_file_path = os.path.join(
      self.temporary_directory.name, 'missing', 'history.csv')
    self.assertFalse(save_battery_resistance_history(new, self.config))
    with open(self.config.summary_file_path, 'r') as summary:
      self.assertEqual(summary.read(), original_summary)
    self.assertFalse(new.battery_resistance_history_row_saved)

  def test_summary_failure_is_recovered_from_committed_history(self):
    missing_directory = os.path.join(
      self.temporary_directory.name, 'missing')
    self.config.summary_file_path = os.path.join(
      missing_directory, 'summary.csv')
    state = self.state(last=84, minimum=70, maximum=100, dirty=True)
    self.assertFalse(save_battery_resistance_history(state, self.config))
    self.assertTrue(state.battery_resistance_history_row_saved)
    loaded = self.state(last=None, minimum=None, maximum=None)
    self.assertTrue(load_battery_resistance_history(loaded, self.config))
    self.assertEqual(loaded.battery_resistance_last_mohm, 84)
    self.assertTrue(loaded.battery_resistance_summary_repair_pending)

  def test_summary_retry_does_not_append_history_twice(self):
    missing_directory = os.path.join(
      self.temporary_directory.name, 'missing')
    self.config.summary_file_path = os.path.join(
      missing_directory, 'summary.csv')
    state = self.state(last=84, minimum=70, maximum=100, dirty=True)
    self.assertFalse(save_battery_resistance_history(state, self.config))
    os.mkdir(missing_directory)
    self.assertTrue(save_battery_resistance_history(state, self.config))
    with open(self.config.history_file_path, 'r') as history:
      self.assertEqual(len(history.readlines()), 2)
    self.assertFalse(state.battery_resistance_history_dirty)
    self.assertFalse(state.battery_resistance_history_row_saved)

  def test_partial_history_tail_is_not_committed(self):
    with open(self.config.history_file_path, 'w') as history:
      history.write('timestamp,resistance_mohm\n')
      history.write('na,83\n')
      history.write('na,9')
    loaded = self.state(last=None, minimum=None, maximum=None)
    self.assertTrue(load_battery_resistance_history(loaded, self.config))
    self.assertEqual(loaded.battery_resistance_last_mohm, 83)
    self.assertEqual(loaded.battery_resistance_min_mohm, 83)
    self.assertEqual(loaded.battery_resistance_max_mohm, 83)

  def test_new_row_is_not_attached_to_partial_history_tail(self):
    with open(self.config.history_file_path, 'w') as history:
      history.write('timestamp,resistance_mohm\n')
      history.write('na,80\n')
      history.write('na,9')
    state = self.state(last=83, minimum=80, maximum=83, dirty=True)
    self.assertTrue(save_battery_resistance_history(state, self.config))
    loaded = self.state(last=None, minimum=None, maximum=None)
    self.assertTrue(load_battery_resistance_history(loaded, self.config))
    self.assertEqual(loaded.battery_resistance_last_mohm, 83)
    self.assertEqual(loaded.battery_resistance_min_mohm, 80)
    self.assertEqual(loaded.battery_resistance_max_mohm, 83)


if __name__ == "__main__":
  unittest.main()
