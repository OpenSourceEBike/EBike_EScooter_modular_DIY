import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
ESPNOW_PATH = ROOT / 'common' / 'espnow.py'


class _FakeEsp:
  def __init__(self, packets):
    self.packets = list(packets)

  def recv(self, timeout):
    if self.packets:
      return self.packets.pop(0)
    return (None, None)


def _load_espnow_module():
  network = types.ModuleType('network')
  espnow = types.ModuleType('espnow')
  urandom = types.ModuleType('urandom')
  urandom.getrandbits = lambda bits: 0
  module_name = 'espnow_receive_bounds_test_module'
  spec = importlib.util.spec_from_file_location(module_name, ESPNOW_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'network': network,
      'espnow': espnow,
      'urandom': urandom,
  }):
    spec.loader.exec_module(module)
  return module


class EspNowReceiveBoundsTests(unittest.TestCase):
  def test_raw_receive_respects_packet_limit(self):
    module = _load_espnow_module()
    esp = _FakeEsp([(b'a', b'1'), (b'b', b'2'), (b'c', b'3')])

    packets = module.espnow_recv_all(esp, max_packets=2)

    self.assertEqual(packets, [(b'a', b'1'), (b'b', b'2')])
    self.assertEqual(esp.packets, [(b'c', b'3')])

  def test_decoded_receive_methods_defer_packets_after_limit(self):
    module = _load_espnow_module()
    comms = module.ESPNowComms.__new__(module.ESPNowComms)
    comms._debug = False
    comms._decoder = lambda message: ('status', message[0], message)
    comms._esp = _FakeEsp([
      (b'a', b'1'), (b'b', b'2'), (b'c', b'3'),
    ])

    latest = comms.get_latest_data_by_source(max_packets=2)

    self.assertEqual(set(latest), {ord('1'), ord('2')})
    self.assertEqual(comms._esp.packets, [(b'c', b'3')])

    comms._esp = _FakeEsp([(b'a', b'1'), (b'b', b'2'), (b'c', b'3')])
    latest_packet = comms.get_latest_data_with_host(max_packets=2)

    self.assertEqual(latest_packet, (b'b', ('status', ord('2'), b'2')))
    self.assertEqual(comms._esp.packets, [(b'c', b'3')])


if __name__ == '__main__':
  unittest.main()
