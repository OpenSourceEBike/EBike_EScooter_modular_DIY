import unittest

from common.bms_battery_resistance import (
  BmsBatteryResistanceEstimator,
  STATE_COMPLETE,
  STATE_REFERENCE,
  bms_resistance_rejection_reason,
)
from common.config_bms_battery_resistance import (
  BmsBatteryResistanceConfig,
  validate_bms_battery_resistance_config,
)


class BmsBatteryResistanceTests(unittest.TestCase):
  def setUp(self):
    self.config = BmsBatteryResistanceConfig()
    self.estimator = BmsBatteryResistanceEstimator(self.config)

  def sample(self, timestamp_ms, voltage_x100, current_x100):
    return self.estimator.update(timestamp_ms, voltage_x100, current_x100)

  def test_default_configuration_is_valid(self):
    self.assertIsNone(validate_bms_battery_resistance_config(self.config))

  def test_sustained_discharge_step_produces_expected_resistance(self):
    # Reference: 53.81 V / -1.30 A; load: 51.70 V / -61.30 A.
    for timestamp in (1000, 3000, 5000):
      self.assertIsNone(self.sample(timestamp, 5381, -130))
    self.assertIsNone(self.sample(7000, 5170, -6130))
    self.assertIsNone(self.sample(9000, 5170, -6130))
    self.assertIsNone(self.sample(11000, 5170, -6130))
    self.assertIsNone(self.sample(13000, 5170, -6130))
    result = self.sample(15000, 5170, -6130)
    self.assertIsNotNone(result)
    self.assertEqual(result[0], 35)
    self.assertEqual(result[1]['delta_voltage_x100'], 211)
    self.assertEqual(result[1]['delta_current_x100'], 6000)
    self.assertEqual(result[1]['load_current_min_x100'], -6130)
    self.assertEqual(result[1]['load_current_max_x100'], -6130)
    self.assertEqual(self.estimator.state, STATE_COMPLETE)

  def test_load_current_range_preserves_negative_jbd_values(self):
    for timestamp in (1000, 3000, 5000):
      self.sample(timestamp, 5381, -130)
    for timestamp, current in ((7000, -6130), (9000, -6130),
                               (11000, -2010), (13000, -2050),
                               (15000, -2100)):
      result = self.sample(timestamp, 5170 if timestamp >= 11000 else 5381,
                           current)
    self.assertIsNotNone(result)
    self.assertEqual(result[1]['load_current_min_x100'], -2100)
    self.assertEqual(result[1]['load_current_max_x100'], -2010)

  def test_reference_requires_three_samples_inside_plus_minus_250_w(self):
    self.assertEqual(self.estimator.state_sample_progress(), (0, 3))
    self.assertIsNone(self.sample(1000, 5000, -500))
    self.assertEqual(self.estimator.state_sample_progress(), (1, 3))
    self.assertIsNone(self.sample(3000, 5000, -500))
    self.assertEqual(self.estimator.state_sample_progress(), (2, 3))
    self.assertIsNone(self.sample(5000, 5000, -500))
    self.assertEqual(self.estimator.state_sample_progress(), (3, 3))

    self.estimator.reset()
    for timestamp in (1000, 3000, 5000):
      self.assertIsNone(self.sample(timestamp, 5000, -500))
    self.assertIsNotNone(self.estimator.baseline)

    self.estimator.reset()
    for timestamp in (1000, 3000, 5000):
      self.assertIsNone(self.sample(timestamp, 5000, -501))
    self.assertIsNone(self.estimator.baseline)

  def test_progress_shows_settle_and_load_samples(self):
    for timestamp in (1000, 3000, 5000):
      self.sample(timestamp, 5381, -130)
    self.sample(7000, 5170, -6130)
    self.assertEqual(self.estimator.state_sample_progress(), (0, 1))
    self.sample(9000, 5170, -6130)
    self.assertEqual(self.estimator.state_sample_progress(), (0, 3))
    self.sample(11000, 5170, -6130)
    self.assertEqual(self.estimator.state_sample_progress(), (1, 3))
    self.sample(13000, 5170, -6130)
    self.assertEqual(self.estimator.state_sample_progress(), (2, 3))
    self.sample(15000, 5170, -6130)
    self.assertEqual(self.estimator.state_sample_progress(), (3, 3))

  def test_load_starts_at_750_w_and_must_remain_a_load(self):
    for timestamp in (1000, 3000, 5000):
      self.assertIsNone(self.sample(timestamp, 5000, -500))
    self.assertIsNotNone(self.estimator.baseline)

    # Exactly -750 W begins the event. A lower subsequent load resets it.
    self.assertIsNone(self.sample(7000, 5000, -1500))
    self.assertNotEqual(self.estimator.state, STATE_REFERENCE)
    self.assertIsNone(self.sample(9000, 5000, -1499))
    self.assertEqual(self.estimator.state, STATE_REFERENCE)

  def test_duplicate_basic_timestamp_is_not_another_sample(self):
    for timestamp in (1000, 3000, 5000, 7000, 9000, 11000):
      self.sample(timestamp, 5381 if timestamp < 7000 else 5170,
                  -130 if timestamp < 7000 else -6130)
    self.sample(11000, 5170, -6130)
    self.assertIsNone(self.sample(13000, 5170, -6130))
    self.assertIsNone(self.sample(13000, 5170, -6130))
    self.assertNotEqual(self.estimator.state, STATE_COMPLETE)

  def test_regeneration_never_looks_like_a_discharge_step(self):
    for timestamp in (1000, 3000, 5000):
      self.sample(timestamp, 5381, -130)
    for timestamp in (7000, 9000, 11000, 13000, 15000):
      self.assertIsNone(self.sample(timestamp, 5450, 2500))
    self.assertEqual(self.estimator.state, STATE_REFERENCE)

  def test_variable_load_current_is_accepted_when_power_stays_above_750_w(self):
    for timestamp in (1000, 3000, 5000):
      self.sample(timestamp, 5381, -130)
    for timestamp, current in ((7000, -6130), (9000, -6130),
                               (11000, -6130), (13000, -5500),
                               (15000, -7000)):
      result = self.sample(timestamp, 5170, current)
    self.assertIsNotNone(result)
    self.assertEqual(self.estimator.state, STATE_COMPLETE)

  def test_load_event_expires_before_a_late_load(self):
    for sample in ((1000, 5400, -100), (3000, 5400, -100),
                   (5000, 5400, -100), (7000, 5200, -3500),
                   (9000, 5200, -3500)):
      self.assertIsNone(self.sample(*sample))

    self.assertIsNone(self.sample(23001, 5200, -3500))
    self.assertEqual(self.estimator.state, STATE_REFERENCE)
    self.assertIsNone(self.estimator.baseline)

  def test_bms_protection_rejects_measurement(self):
    self.assertEqual(
      bms_resistance_rejection_reason(['over-current']),
      'BMS protection active')
    self.assertEqual(
      bms_resistance_rejection_reason([]), '')

if __name__ == '__main__':
  unittest.main()
