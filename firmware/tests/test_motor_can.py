import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
import time


class FakeCAN:
  frames = []

  def __init__(self, **kwargs):
    self.sent = []
    self.recv_calls = 0
    self.frames = list(type(self).frames)

  def send(self, buf, msg_id, extframe=False, timeout=None):
    self.sent.append((bytes(buf), msg_id, extframe, timeout))

  def recv(self):
    self.recv_calls += 1
    if self.frames:
      return self.frames.pop(0)
    return None


fake_can_module = types.ModuleType('can')
fake_can_module.CAN = FakeCAN
sys.modules.setdefault('can', fake_can_module)

module_path = pathlib.Path(__file__).parents[1] / '01_diy_main_board' / 'motor.py'
spec = importlib.util.spec_from_file_location('motor_can_under_test', module_path)
motor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motor_module)


class MotorCanTimingTests(unittest.TestCase):
  def setUp(self):
    self.sleep_calls = []
    self.original_sleep_ms = getattr(time, 'sleep_ms', None)
    time.sleep_ms = self.sleep_calls.append
    motor_module.Motor._can = None
    FakeCAN.frames = []
    cfg = SimpleNamespace(can_tx_pin=1, can_rx_pin=2, can_baudrate=500000,
                          can_mode=0, can_id=10)
    self.data = motor_module.MotorData(cfg)
    self.motor = motor_module.Motor(self.data)

  def tearDown(self):
    if self.original_sleep_ms is None:
      del time.sleep_ms
    else:
      time.sleep_ms = self.original_sleep_ms

  def test_tx_keeps_required_post_send_delay(self):
    self.motor.set_motor_speed_erpm(1234)
    self.assertEqual(len(self.motor._can.sent), 1)
    self.assertEqual(self.motor._can.sent[0][3], 0)
    self.assertEqual(self.sleep_calls, [3])

  def test_empty_rx_queue_returns_after_one_nonblocking_probe(self):
    self.assertEqual(self.motor.update_motor_data(self.motor), 0)
    self.assertEqual(self.motor._can.recv_calls, 1)

  def test_rx_work_is_bounded_by_frame_count(self):
    self.motor._can.frames = [
      (0x7f, True, False, b'\x00') for _ in range(50)
    ]
    self.assertEqual(
      self.motor.update_motor_data(self.motor, max_frames=5), 5)
    self.assertEqual(len(self.motor._can.frames), 45)


if __name__ == '__main__':
  unittest.main()
