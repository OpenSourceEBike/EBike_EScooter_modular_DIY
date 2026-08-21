import time
import unittest
import os
import tempfile
from types import SimpleNamespace


if not hasattr(time, "ticks_diff"):
  time.ticks_diff = lambda newer, older: newer - older

from common.battery_resistance import (
  BatteryResistanceEstimator,
  BatteryResistanceMonitor,
  aggregate_battery_measurements,
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
    config.boot_qualifying_seconds = 0
    config.reference_qualify_ms = 0
    config.load_qualify_ms = 5000
    return config

  def start_attempt(self, monitor, start_ms=0):
    monitor.update(start_ms, 5400, 300, 0)
    monitor.update(start_ms + 500, 5400, 300, 0)
    monitor.update(start_ms + 1000, 5400, 300, 0)
    monitor.update(start_ms + 1100, 5300, 1600, 0)

  def feed(self, monitor, times_ms, voltage_x100=5300, current_x100=1600):
    result = None
    for now in times_ms:
      value = monitor.update(now, voltage_x100, current_x100, 0)
      if value is not None:
        result = value
    return result

  def test_first_three_samples_at_500_ms_spacing(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = self.feed(monitor, range(1600, 7601, 500))
    self.assertEqual(result, 76)
    self.assertTrue(monitor.completed)

  def test_one_observation_per_second_is_enough(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = self.feed(monitor, range(2100, 9101, 1000))
    self.assertEqual(result, 76)

  def test_boot_qualification_counts_one_valid_power_sample_per_second(self):
    config = BatteryResistanceConfig()
    config.boot_qualifying_seconds = 2
    config.reference_qualify_ms = 0
    config.load_qualify_ms = 5000
    monitor = BatteryResistanceMonitor(config)
    # Two 4 A, 54 V samples in the same elapsed second count only once.
    monitor.update(100, 5400, 400, 0)
    monitor.update(900, 5400, 400, 0)
    self.assertFalse(monitor.completed)

    # A qualifying sample in the next second enables reference qualification.
    monitor.update(1100, 5400, 400, 0)
    monitor.update(1200, 5400, 300, 0)
    monitor.update(1700, 5400, 300, 0)
    monitor.update(2200, 5400, 300, 0)
    monitor.update(2300, 5300, 1600, 0)
    result = None
    for now in range(2800, 8801, 500):
      value = monitor.update(now, 5300, 1600, 0)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_reference_qualification_requires_continuous_low_power(self):
    config = self.make_config()
    config.reference_qualify_ms = 2000
    monitor = BatteryResistanceMonitor(config)
    monitor.update(100, 5400, 300, 0)
    monitor.update(900, 5300, 1600, 0)
    monitor.update(1100, 5400, 300, 0)
    monitor.update(2100, 5400, 300, 0)
    monitor.update(3100, 5400, 300, 0)
    monitor.update(3600, 5400, 300, 0)
    monitor.update(4100, 5400, 300, 0)
    monitor.update(4200, 5300, 1600, 0)
    self.assertEqual(
      self.feed(monitor, range(4700, 10701, 500)),
      76,
    )

  def test_reference_qualification_restarts_when_one_second_is_missing(self):
    config = self.make_config()
    config.reference_qualify_ms = 2000
    monitor = BatteryResistanceMonitor(config)
    monitor.update(0, 5400, 300, 0)
    monitor.update(2000, 5400, 300, 0)

    monitor.update(2100, 5400, 300, 0)
    monitor.update(3100, 5400, 300, 0)
    monitor.update(4100, 5400, 300, 0)
    monitor.update(4600, 5400, 300, 0)
    monitor.update(5100, 5400, 300, 0)
    monitor.update(5200, 5300, 1600, 0)
    self.assertEqual(
      self.feed(monitor, range(5700, 11701, 500)),
      76,
    )

  def test_one_implausible_calculation_is_skipped(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = None
    for now in range(1600, 8101, 500):
      voltage = 5500 if now == 6100 else 5300
      value = monitor.update(now, voltage, 1600, 0)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_gap_resets_attempt_but_allows_retry(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    monitor.update(2100, 5300, 1600, 0)
    self.assertTrue(monitor.expire_observation_gap(4101))

    self.start_attempt(monitor, 3800)
    result = self.feed(monitor, range(5400, 11401, 500))
    self.assertEqual(result, 76)

  def test_power_drop_resets_attempt_but_allows_retry(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    monitor.update(2100, 5300, 1400, 0)

    self.start_attempt(monitor, 2200)
    result = self.feed(monitor, range(3800, 9801, 500))
    self.assertEqual(result, 76)

  def test_below_load_and_regen_reset_only_current_attempt(self):
    for current, regen in ((1400, False), (1600, True)):
      monitor = BatteryResistanceMonitor(self.make_config())
      self.start_attempt(monitor)
      monitor.update(2100, 5300, current, 0, regen_active=regen)
      self.start_attempt(monitor, 2200)
      result = self.feed(monitor, range(3800, 9801, 500))
      self.assertEqual(result, 76)

  def test_completed_result_is_stable(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = self.feed(monitor, range(1600, 7601, 500))
    self.assertEqual(result, 76)
    self.assertIsNone(monitor.update(7000, 5000, 2000, 0))
    self.assertEqual(monitor.result_mohm, 76)

  def test_default_reference_qualifies_for_fifteen_seconds_then_load_for_ten(self):
    config = BatteryResistanceConfig()
    config.boot_qualifying_seconds = 0
    monitor = BatteryResistanceMonitor(config)
    for now in range(0, 15001, 1000):
      self.assertIsNone(monitor.update(now, 5400, 300, 0))
    self.assertIsNone(monitor.update(15500, 5400, 300, 0))
    self.assertIsNone(monitor.update(16000, 5400, 300, 0))
    self.assertIsNone(monitor.update(16100, 5300, 1600, 0))
    for now in range(17100, 26100, 1000):
      self.assertIsNone(monitor.update(now, 5300, 1600, 0))
    self.assertEqual(monitor.update(26100, 5300, 1600, 0), 76)
    self.assertIsNone(monitor.update(26600, 5300, 1600, 0))
    self.assertEqual(monitor.result_mohm, 76)

  def test_dual_motor_currents_are_summed_and_voltage_is_weighted(self):
    self.assertEqual(
      aggregate_battery_measurements(((540, 100), (530, 200))),
      (5330, 3000),
    )

  def test_zero_current_reference_uses_mean_dual_vesc_voltage(self):
    self.assertEqual(
      aggregate_battery_measurements(((540, 0), (530, 0))),
      (5350, 0),
    )

  def test_invalid_or_regen_branch_rejects_dual_motor_sample(self):
    self.assertIsNone(
      aggregate_battery_measurements(((540, 100), (530, -1))))
    self.assertIsNone(
      aggregate_battery_measurements(((540, 0), (0, 0))))
    self.assertIsNone(
      aggregate_battery_measurements(((540, 100), (None, None))))

  def test_coercible_but_malformed_input_is_rejected(self):
    self.assertIsNone(
      aggregate_battery_measurements(((540.0, 100), (530, 200))))
    self.assertIsNone(
      aggregate_battery_measurements((("540", 100), (530, 200))))

    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    monitor.update(1600, 5300.0, 1600, 0)
    self.assertFalse(monitor.completed)

    self.start_attempt(monitor, 1700)
    self.assertEqual(
      self.feed(monitor, range(3300, 9301, 500)),
      76,
    )


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
    config.boot_qualifying_seconds = 0
    config.reference_qualify_ms = 0
    config.load_qualify_ms = 5000
    return BatteryResistanceEstimator(config, 0)

  def precision_sample(self, estimator, data, timestamp_ms,
                       current_x1000, voltage_x1000):
    data.precision(timestamp_ms, voltage_x1000, current_x1000)
    return estimator.update(timestamp_ms, (data,))

  def dual_precision_sample(self, estimator, rear, front, start_ms,
                            rear_current_x1000, front_current_x1000,
                            rear_voltage_x1000, front_voltage_x1000):
    rear.precision(start_ms, rear_voltage_x1000, rear_current_x1000)
    estimator.update(start_ms, (rear, front))
    front.precision(start_ms + 20, front_voltage_x1000, front_current_x1000)
    return estimator.update(start_ms + 20, (rear, front))

  def start_precision_attempt(self, estimator, data, start_ms=100):
    self.precision_sample(estimator, data, start_ms, 3000, 54000)
    self.precision_sample(estimator, data, start_ms + 500, 3000, 54000)
    self.precision_sample(estimator, data, start_ms + 1000, 3000, 54000)
    return self.precision_sample(
      estimator, data, start_ms + 1100, 16000, 53000)

  def start_dual_precision_attempt(self, estimator, rear, front, start_ms=100):
    for timestamp_ms in (start_ms, start_ms + 500, start_ms + 1000):
      self.dual_precision_sample(
        estimator, rear, front, timestamp_ms, 1000, 2000, 54000, 54000)
    return self.dual_precision_sample(
      estimator, rear, front, start_ms + 1100, 6000, 10000, 53000, 53000)

  def test_atomic_precision_samples_complete_attempt(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.start_precision_attempt(estimator, data)

    result = None
    for timestamp_ms in range(2200, 9001, 1000):
      value = self.precision_sample(
        estimator, data, timestamp_ms, 16000, 53000)
      if value is not None:
        result = value
    self.assertEqual(result, 76)
    self.assertTrue(estimator.completed)

  def test_zero_current_precision_reference_is_accepted(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    for timestamp_ms in (100, 600, 1100):
      self.precision_sample(estimator, data, timestamp_ms, 0, 54000)
    self.precision_sample(estimator, data, 1200, 16000, 53000)

    result = None
    for timestamp_ms in range(2200, 9001, 1000):
      value = self.precision_sample(
        estimator, data, timestamp_ms, 16000, 53000)
      if value is not None:
        result = value
    self.assertEqual(result, 62)

  def test_current_drop_resets_active_precision_attempt(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.start_precision_attempt(estimator, data)

    self.precision_sample(estimator, data, 2000, 14000, 53000)
    for timestamp_ms in range(3000, 9001, 1000):
      self.precision_sample(estimator, data, timestamp_ms, 16000, 53000)
    self.assertFalse(estimator.completed)

    self.start_precision_attempt(estimator, data, 10000)
    result = None
    for timestamp_ms in range(12100, 19101, 1000):
      value = self.precision_sample(
        estimator, data, timestamp_ms, 16000, 53000)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_dual_vesc_precision_samples_complete(self):
    estimator = self.make_estimator()
    rear = FakeMotorData()
    front = FakeMotorData()
    self.start_dual_precision_attempt(estimator, rear, front)

    result = None
    for start_ms in range(2200, 9001, 1000):
      value = self.dual_precision_sample(
        estimator, rear, front, start_ms, 6000, 10000, 53000, 53000)
      if value is not None:
        result = value
    self.assertEqual(result, 76)


class BatteryResistanceConfigTests(unittest.TestCase):
  def test_non_integer_measurement_value_is_rejected(self):
    config = BatteryResistanceConfig()
    config.boot_qualifying_seconds = float("nan")
    self.assertIsNotNone(
      validate_battery_resistance_measurement_config(config))

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
      'last,84,na\n',
      'min,70,na\n',
      'max,100,na\n',
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
