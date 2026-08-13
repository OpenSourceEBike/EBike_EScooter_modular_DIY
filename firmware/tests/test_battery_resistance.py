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
    config.boot_delay_ms = 0
    return config

  def start_attempt(self, monitor, start_ms=0):
    monitor.update(start_ms, 5400, 300, 0)
    monitor.update(start_ms + 100, 5300, 1600, 0)

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
    result = self.feed(monitor, range(600, 6601, 500))
    self.assertEqual(result, 76)
    self.assertTrue(monitor.completed)

  def test_one_observation_per_second_is_enough(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = self.feed(monitor, range(1100, 8101, 1000))
    self.assertEqual(result, 76)

  def test_default_three_minute_boot_delay_is_enforced(self):
    config = BatteryResistanceConfig()
    monitor = BatteryResistanceMonitor(config)
    monitor.update(179000, 5400, 300, 0)
    monitor.update(179500, 5300, 1600, 0)
    self.assertFalse(monitor.completed)

    monitor.update(180000, 5400, 300, 0)
    monitor.update(180100, 5300, 1600, 0)
    result = None
    for now in range(180600, 186601, 500):
      value = monitor.update(now, 5300, 1600, 0)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_one_implausible_calculation_is_skipped(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = None
    for now in range(600, 7101, 500):
      voltage = 5500 if now == 5100 else 5300
      value = monitor.update(now, voltage, 1600, 0)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_gap_resets_attempt_but_allows_retry(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    monitor.update(1100, 5300, 1600, 0)
    self.assertTrue(monitor.expire_observation_gap(2701))

    monitor.update(2800, 5400, 300, 0)
    monitor.update(2900, 5300, 1600, 0)
    result = self.feed(monitor, range(3400, 9401, 500))
    self.assertEqual(result, 76)

  def test_unstable_current_resets_attempt_but_allows_retry(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    monitor.update(1100, 5300, 1901, 0)

    monitor.update(1200, 5400, 300, 0)
    monitor.update(1300, 5300, 1600, 0)
    result = self.feed(monitor, range(1800, 7801, 500))
    self.assertEqual(result, 76)

  def test_below_load_and_regen_reset_only_current_attempt(self):
    for current, regen in ((1400, False), (1600, True)):
      monitor = BatteryResistanceMonitor(self.make_config())
      self.start_attempt(monitor)
      monitor.update(1100, 5300, current, 0, regen_active=regen)
      monitor.update(1200, 5400, 300, 0)
      monitor.update(1300, 5300, 1600, 0)
      result = self.feed(monitor, range(1800, 7801, 500))
      self.assertEqual(result, 76)

  def test_completed_result_is_stable(self):
    monitor = BatteryResistanceMonitor(self.make_config())
    self.start_attempt(monitor)
    result = self.feed(monitor, range(600, 6601, 500))
    self.assertEqual(result, 76)
    self.assertIsNone(monitor.update(7000, 5000, 2000, 0))
    self.assertEqual(monitor.result_mohm, 76)

  def test_dual_motor_currents_are_summed_and_voltage_is_weighted(self):
    self.assertEqual(
      aggregate_battery_measurements(((540, 100), (530, 200))),
      (5330, 3000),
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
    monitor.update(600, 5300.0, 1600, 0)
    self.assertFalse(monitor.completed)

    monitor.update(700, 5400, 300, 0)
    monitor.update(800, 5300, 1600, 0)
    self.assertEqual(
      self.feed(monitor, range(1300, 7301, 500)),
      76,
    )


class FakeMotorData:
  def __init__(self):
    self.battery_pair_update_counter = 0
    self.status_4_last_update_ms = 0
    self.status_5_last_update_ms = 0
    self.battery_current_measurement_x10 = None
    self.battery_voltage_measurement_x10 = None

  def current(self, timestamp_ms, current_x10):
    self.status_4_last_update_ms = timestamp_ms
    self.battery_current_measurement_x10 = current_x10
    self.battery_pair_update_counter += 1

  def voltage(self, timestamp_ms, voltage_x10):
    self.status_5_last_update_ms = timestamp_ms
    self.battery_voltage_measurement_x10 = voltage_x10
    self.battery_pair_update_counter += 1


class BatteryResistanceEstimatorTests(unittest.TestCase):
  def make_estimator(self):
    config = BatteryResistanceConfig()
    config.boot_delay_ms = 0
    return BatteryResistanceEstimator(config, 0)

  def phased_pair(self, estimator, data, current_ms, voltage_ms,
                  current_x10, voltage_x10):
    data.current(current_ms, current_x10)
    estimator.update(current_ms, (data,))
    data.voltage(voltage_ms, voltage_x10)
    return estimator.update(voltage_ms, (data,))

  def dual_phased_pair(self, estimator, rear, front, start_ms,
                       rear_current_x10, front_current_x10,
                       rear_voltage_x10, front_voltage_x10):
    rear.current(start_ms, rear_current_x10)
    estimator.update(start_ms, (rear, front))
    front.current(start_ms + 20, front_current_x10)
    estimator.update(start_ms + 20, (rear, front))
    rear.voltage(start_ms + 100, rear_voltage_x10)
    estimator.update(start_ms + 100, (rear, front))
    front.voltage(start_ms + 120, front_voltage_x10)
    return estimator.update(start_ms + 120, (rear, front))

  def test_phased_status_4_status_5_pairs_do_not_reset_attempt(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.phased_pair(estimator, data, 100, 200, 30, 540)
    self.phased_pair(estimator, data, 1000, 1100, 160, 530)

    result = None
    for current_ms in range(2000, 8001, 1000):
      value = self.phased_pair(
        estimator, data, current_ms, current_ms + 100, 160, 530)
      if value is not None:
        result = value
    self.assertEqual(result, 76)
    self.assertTrue(estimator.completed)

  def test_current_drop_resets_while_voltage_half_is_pending(self):
    estimator = self.make_estimator()
    data = FakeMotorData()
    self.phased_pair(estimator, data, 100, 200, 30, 540)
    self.phased_pair(estimator, data, 1000, 1100, 160, 530)

    # The old voltage is over-skew when this current arrives. The tracker must
    # still use the current-only evidence to cancel the active plateau.
    self.phased_pair(estimator, data, 2000, 2100, 140, 530)
    for current_ms in range(3000, 9001, 1000):
      self.phased_pair(
        estimator, data, current_ms, current_ms + 100, 160, 530)
    self.assertFalse(estimator.completed)

    self.phased_pair(estimator, data, 10000, 10100, 30, 540)
    self.phased_pair(estimator, data, 10900, 11000, 160, 530)
    result = None
    for current_ms in range(11900, 17901, 1000):
      value = self.phased_pair(
        estimator, data, current_ms, current_ms + 100, 160, 530)
      if value is not None:
        result = value
    self.assertEqual(result, 76)

  def test_dual_vesc_independent_half_frames_complete(self):
    estimator = self.make_estimator()
    rear = FakeMotorData()
    front = FakeMotorData()
    self.dual_phased_pair(estimator, rear, front, 100, 10, 20, 540, 540)
    self.dual_phased_pair(estimator, rear, front, 1000, 60, 100, 530, 530)

    result = None
    for start_ms in range(2000, 8001, 1000):
      value = self.dual_phased_pair(
        estimator, rear, front, start_ms, 60, 100, 530, 530)
      if value is not None:
        result = value
    self.assertEqual(result, 76)


class BatteryResistanceConfigTests(unittest.TestCase):
  def test_non_integer_measurement_value_is_rejected(self):
    config = BatteryResistanceConfig()
    config.boot_delay_ms = float("nan")
    self.assertIsNotNone(
      validate_battery_resistance_measurement_config(config))

  def test_dual_vesc_skew_cannot_exceed_source_age(self):
    config = BatteryResistanceConfig()
    config.dual_vesc_max_skew_ms = config.vesc_signal_max_age_ms + 1
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
