import unittest

from common.motor_telemetry import (
  aggregate_battery_status,
  clear_stale_status_1,
  clear_stale_status_4,
  refresh_wheel_speed,
  select_wheel_speed,
)
from types import SimpleNamespace


class MotorTelemetryTests(unittest.TestCase):
  def test_same_erpm_recovers_wheel_speed_after_status_1_expires(self):
    for poles_pair in (15, 20):
      with self.subTest(poles_pair=poles_pair):
        data = SimpleNamespace(
          cfg=SimpleNamespace(wheel_radius=0.1, poles_pair=poles_pair),
          speed_erpm=3000,
          wheel_speed=0,
          wheel_speed_last_erpm=None,
          motor_current_x10=120,
        )
        refresh_wheel_speed(data)
        original_speed = data.wheel_speed
        self.assertGreater(original_speed, 0)

        clear_stale_status_1(data)
        self.assertEqual(data.wheel_speed, 0)
        self.assertIsNone(data.wheel_speed_last_erpm)
        self.assertEqual(data.motor_current_x10, 0)

        # A CAN frame with the original ERPM arrives before the next 100 ms pass.
        data.speed_erpm = 3000
        refresh_wheel_speed(data)
        self.assertEqual(data.wheel_speed, original_speed)
        self.assertEqual(data.wheel_speed_last_erpm, 3000)

  def test_unchanged_erpm_keeps_cached_wheel_speed(self):
    data = SimpleNamespace(
      cfg=SimpleNamespace(wheel_radius=0.1, poles_pair=15),
      speed_erpm=3000,
      wheel_speed=7.5,
      wheel_speed_last_erpm=3000,
    )
    refresh_wheel_speed(data)
    self.assertEqual(data.wheel_speed, 7.5)

  def test_rear_speed_is_preferred_when_both_are_fresh(self):
    self.assertEqual(select_wheel_speed(31, True, 29, True), 31)

  def test_front_speed_is_used_when_rear_is_stale(self):
    self.assertEqual(select_wheel_speed(0, False, 29, True), 29)

  def test_speed_is_zero_only_when_both_sources_are_stale(self):
    self.assertEqual(select_wheel_speed(31, False, 29, False), 0)

  def test_dual_battery_status_uses_both_fresh_branches(self):
    self.assertEqual(
      aggregate_battery_status(800, 150, True, 760, 100, True),
      (784, 250),
    )

  def test_front_battery_is_a_fallback_when_rear_is_stale(self):
    self.assertEqual(
      aggregate_battery_status(0, 0, False, 760, 100, True),
      (760, 100),
    )

  def test_battery_status_is_zero_only_when_both_sources_are_stale(self):
    self.assertEqual(
      aggregate_battery_status(800, 150, False, 760, 100, False),
      (0, 0),
    )

  def test_stale_status_4_keeps_temperatures_unavailable(self):
    data = SimpleNamespace(
      battery_current_x10=123,
      vesc_temperature_x10=250,
      motor_temperature_x10=300,
    )
    clear_stale_status_4(data, -2550)
    self.assertEqual(data.battery_current_x10, 0)
    self.assertEqual(data.vesc_temperature_x10, -2550)
    self.assertEqual(data.motor_temperature_x10, -2550)


if __name__ == '__main__':
  unittest.main()
