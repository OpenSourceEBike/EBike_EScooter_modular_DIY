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

  def gap_disconnect(self, connection):
    self.disconnected = connection


def _basic_frame(checksum_start=2, status=0):
  data = bytearray(23)
  data[0:2] = bytes((0x1C, 0x20))  # 72.00 V
  data[2:4] = bytes((0xFF, 0x9C))  # -1.00 A
  data[19] = 50
  data[21] = 20
  data[22] = 0
  prefix = bytes((0xDD, 0x03, status, len(data))) + bytes(data)
  checksum = (-sum(prefix[checksum_start:])) & 0xFFFF
  return prefix + bytes((checksum >> 8, checksum & 0xFF, 0x77))


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

  def test_connection_failure_discards_complete_old_basic_frame(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    client._started = True
    client.conn = 7
    client._push_bytes(_basic_frame())

    client._handle_connection_failure('test disconnect')

    self.assertEqual(client._buf, bytearray())
    self.assertEqual(client._head, 0)
    client.conn = 8
    client.h_n = 9
    client._scan_active = False
    client._connecting = False
    self.assertFalse(client._drain_frames())
    self.assertIsNone(client.get_battery_voltage_x100())

  def test_connection_failure_discards_partial_old_frame(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    client._started = True
    client._push_bytes(_basic_frame()[:12])

    client._handle_connection_failure('partial frame')
    client._push_bytes(_basic_frame())

    self.assertTrue(client._drain_frames())
    self.assertEqual(client.get_battery_voltage_x100(), 7200)
    self.assertEqual(client.get_current_a_x100(), -100)

  def test_connection_failure_discards_cached_measurements(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    client._started = True
    client._push_bytes(_basic_frame())

    self.assertTrue(client._drain_frames())
    self.assertEqual(client.get_battery_voltage_x100(), 7200)

    client._handle_connection_failure('cached data')

    self.assertIsNone(client.get_battery_voltage_x100())
    self.assertIsNone(client.get_current_a_x100())
    self.assertIsNone(client.get_cells_x1000())
    self.assertFalse(client.is_basic_fresh())

  def test_only_canonical_jbd_checksum_range_is_accepted(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())

    canonical = _basic_frame(checksum_start=2)
    includes_command = _basic_frame(checksum_start=1)

    self.assertTrue(client._frame_ok(canonical))
    self.assertIsNotNone(client._parse_basic(canonical))
    self.assertFalse(client._frame_ok(includes_command))
    self.assertIsNone(client._parse_basic(includes_command))

  def test_non_success_jbd_status_is_rejected(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    frame = _basic_frame(status=1)

    self.assertFalse(client._frame_ok(frame))
    self.assertIsNone(client._parse_basic(frame))

  def test_declared_jbd_payload_length_must_match_complete_frame(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    frame = bytearray(_basic_frame())
    frame[3] -= 1
    checksum = (-sum(frame[2:-3])) & 0xFFFF
    frame[-3] = checksum >> 8
    frame[-2] = checksum & 0xFF

    self.assertFalse(client._frame_ok(frame))
    self.assertIsNone(client._parse_basic(frame))

  def test_bad_terminator_preserves_following_frame_start(self):
    module = _load_bms_jbd_module()
    client = module.JbdBmsClient(ble=_FakeBle())
    malformed = bytearray(_basic_frame())
    malformed[-1] = 0
    expected = _basic_frame()
    client._push_bytes(malformed + expected)

    frame = client._pop_frame()

    self.assertEqual(frame, expected)
    self.assertIsNotNone(client._parse_basic(frame))


if __name__ == '__main__':
  unittest.main()
