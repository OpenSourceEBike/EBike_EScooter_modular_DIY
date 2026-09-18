import unittest

from common.motor_telemetry import (
  aggregate_battery_status,
  clear_stale_status_4,
  select_wheel_speed,
)
from types import SimpleNamespace


class MotorTelemetryTests(unittest.TestCase):
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
