import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
THROTTLE_PATH = ROOT / '01_diy_main_board' / 'throttle.py'


class _FakePin:
  def __init__(self, number):
    self.number = number


class _FakeAdc:
  next_value = 0

  def __init__(self, pin):
    self.pin = pin

  def read_u16(self):
    return self.next_value


def _load_throttle_module():
  machine = types.ModuleType('machine')
  machine.ADC = _FakeAdc
  machine.Pin = _FakePin
  spec = importlib.util.spec_from_file_location(
    'throttle_refresh_test_module', THROTTLE_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'machine': machine,
  }):
    spec.loader.exec_module(module)
  return module


class ThrottleRefreshTests(unittest.TestCase):
  def test_refresh_updates_scalars_and_value_keeps_compatibility(self):
    module = _load_throttle_module()
    throttle = module.Throttle(1, min_val=100, max_val=1100)

    _FakeAdc.next_value = 600
    self.assertIsNone(throttle.refresh())
    self.assertEqual(throttle.raw_value, 600)
    self.assertEqual(throttle.scaled_value, 500)

    _FakeAdc.next_value = 1100
    self.assertEqual(throttle.value, (1100, 1000))

    _FakeAdc.next_value = 99
    throttle.refresh()
    self.assertEqual(throttle.scaled_value, 0)


if __name__ == '__main__':
  unittest.main()
