import importlib.util
import inspect
import asyncio
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
WIFI_TIME_SYNC_PATH = ROOT / '02_diy_display' / 'wifi_time_sync.py'


def _load_wifi_time_sync_module():
  network = types.ModuleType('network')
  network.STA_IF = 0
  network.AP_IF = 1
  ntptime = types.ModuleType('ntptime')
  module_name = 'wifi_time_sync_test_module'
  spec = importlib.util.spec_from_file_location(
    module_name, WIFI_TIME_SYNC_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'network': network,
      'ntptime': ntptime,
  }):
    spec.loader.exec_module(module)
  return module


class WifiTimeSyncTests(unittest.TestCase):
  def test_dns_query_response_parser_returns_first_ipv4_answer(self):
    module = _load_wifi_time_sync_module()
    transaction_id = 0x1234
    query = module._build_dns_query('pool.ntp.org', transaction_id)
    response = (
      bytes((0x12, 0x34, 0x81, 0x80, 0x00, 0x01, 0x00, 0x01,
             0x00, 0x00, 0x00, 0x00)) +
      query[12:] +
      bytes((0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01,
             0x00, 0x00, 0x00, 0x3C, 0x00, 0x04,
             192, 0, 2, 123))
    )

    self.assertEqual(
      module._parse_dns_ipv4_response(response, transaction_id),
      '192.0.2.123')
    self.assertIsNone(
      module._parse_dns_ipv4_response(response, transaction_id + 1))

  def test_ntp_epoch_conversion_handles_host_epoch(self):
    module = _load_wifi_time_sync_module()
    utc_now = module._ntp_seconds_to_utc(
      module.NTP_TO_2000_EPOCH_SECONDS)

    self.assertEqual(tuple(utc_now[:6]), (2000, 1, 1, 0, 0, 0))

  def test_async_connect_path_has_no_explicit_wifi_scan(self):
    module = _load_wifi_time_sync_module()
    source = inspect.getsource(module._connect_wifi_attempt_async)

    self.assertIn('await _prepare_wifi_station_async', source)
    self.assertNotIn('_log_wifi_scan', source)

  def test_async_ntp_path_does_not_call_blocking_ntptime(self):
    module = _load_wifi_time_sync_module()
    source = inspect.getsource(module.sync_rtc_time_from_wifi_ntp_async)

    self.assertIn('await _set_rtc_from_ntp_async', source)
    self.assertNotIn('ntptime.settime', source)

  def test_async_ntp_response_sets_internal_rtc_under_one_deadline(self):
    module = _load_wifi_time_sync_module()
    deadlines = []

    async def resolve_ipv4(_sta, host, deadline_ms):
      self.assertEqual(host, 'pool.ntp.org')
      deadlines.append(deadline_ms)
      return '192.0.2.123'

    async def udp_exchange(payload, address, deadline_ms, response_size):
      self.assertEqual(address, ('192.0.2.123', module.NTP_PORT))
      self.assertEqual(len(payload), module.NTP_PACKET_SIZE)
      self.assertEqual(response_size, module.NTP_PACKET_SIZE)
      deadlines.append(deadline_ms)
      response = bytearray(module.NTP_PACKET_SIZE)
      response[0] = 0x24  # NTP version 4, server mode.
      response[1] = 2
      response[40:44] = module.NTP_TO_2000_EPOCH_SECONDS.to_bytes(4, 'big')
      return bytes(response)

    class Rtc:
      def __init__(self):
        self.saved = None

      def set_internal_utc(self, utc_now):
        self.saved = utc_now

      def internal_utc_now(self):
        return self.saved

    rtc = Rtc()
    with (
        patch.object(module.time, 'ticks_ms', return_value=100, create=True),
        patch.object(
          module.time, 'ticks_add', side_effect=lambda value, delta: value + delta,
          create=True),
        patch.object(module, '_resolve_ipv4_async', new=resolve_ipv4),
        patch.object(module, '_udp_exchange_async', new=udp_exchange)):
      utc_now = asyncio.run(module._set_rtc_from_ntp_async(
        rtc, object(), 'pool.ntp.org', 3))

    self.assertEqual(tuple(utc_now[:6]), (2000, 1, 1, 0, 0, 0))
    self.assertEqual(deadlines, [3100, 3100])
    self.assertIs(rtc.saved, utc_now)


if __name__ == '__main__':
  unittest.main()
