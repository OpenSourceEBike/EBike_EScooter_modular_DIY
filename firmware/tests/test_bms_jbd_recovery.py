import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
BMS_JBD_PATH = ROOT / '02_diy_display' / 'bms_jbd.py'


class _FakeTime:
  now = 1000

  @classmethod
  def ticks_ms(cls):
    return cls.now

  @staticmethod
  def ticks_add(value, delta):
    return value + delta

  @staticmethod
  def ticks_diff(left, right):
    return left - right


class _FakeBle:
  def __init__(self):
    self.is_active = False
    self.scans = []

  def active(self, value=None):
    if value is not None:
      self.is_active = bool(value)
    return self.is_active

  def irq(self, callback):
    self.callback = callback

  def gap_scan(self, duration, *args):
    self.scans.append(duration)


def _load_bms_jbd_module():
  bluetooth = types.ModuleType('bluetooth')
  bluetooth.BLE = _FakeBle
  bluetooth.UUID = lambda value: value
  micropython = types.ModuleType('micropython')
  micropython.const = lambda value: value
  module_name = 'bms_jbd_recovery_test_module'
  spec = importlib.util.spec_from_file_location(module_name, BMS_JBD_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'bluetooth': bluetooth,
      'micropython': micropython,
  }):
    spec.loader.exec_module(module)
  module.time = _FakeTime
  return module


class JbdBmsRecoveryTests(unittest.TestCase):
  def setUp(self):
    _FakeTime.now = 1000

  def test_unavailable_bms_retries_after_backoff(self):
    module = _load_bms_jbd_module()
    ble = _FakeBle()
    client = module.JbdBmsClient(ble=ble)
    client.start()
    client._scan_active = False
    client._retry_count = module.MAX_RECONNECT_ATTEMPTS
    client._retry_or_unavailable('test')

    self.assertTrue(client._unavailable)
    _FakeTime.now += module.RECONNECT_BACKOFF_MS
    client.tick()

    self.assertFalse(client._unavailable)
    self.assertEqual(client._retry_count, 0)
    self.assertTrue(client._scan_active)

  def test_repeated_tick_exceptions_enter_connection_recovery(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    client._started = True
    client._drain_frames = lambda: (_ for _ in ()).throw(RuntimeError('bad'))
    failures = []
    client._handle_connection_failure = failures.append

    for _ in range(module.MAX_CONSECUTIVE_TICK_EXCEPTIONS):
      client.tick()

    self.assertEqual(failures, ['repeated tick exception'])
    self.assertEqual(client._tick_exception_count, 0)


if __name__ == '__main__':
  unittest.main()
