import importlib.util
import pathlib
import sys
import time
import types
import unittest
from types import SimpleNamespace


class FakeCAN:
  frames = []
  def __init__(self, **kwargs):
    self.sent, self.recv_calls = [], 0
    self.frames = list(type(self).frames)
  def send(self, buf, msg_id, extframe=False, timeout=None):
    self.sent.append((bytes(buf), msg_id, extframe, timeout))
  def recv(self):
    self.recv_calls += 1
    return self.frames.pop(0) if self.frames else None


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
    self.original_ticks_ms = getattr(time, 'ticks_ms', None)
    time.sleep_ms, time.ticks_ms = self.sleep_calls.append, lambda: 1234
    motor_module.Motor._can, FakeCAN.frames = None, []
    self.data = motor_module.MotorData(SimpleNamespace(
      can_tx_pin=1, can_rx_pin=2, can_baudrate=500000, can_mode=0, can_id=10))
    self.motor = motor_module.Motor(self.data)
  def tearDown(self):
    if self.original_sleep_ms is None: del time.sleep_ms
    else: time.sleep_ms = self.original_sleep_ms
    if self.original_ticks_ms is None: del time.ticks_ms
    else: time.ticks_ms = self.original_ticks_ms
  def test_tx_keeps_required_post_send_delay(self):
    self.motor.set_motor_speed_erpm(1234)
    self.assertEqual(self.sleep_calls, [3])
  def test_standard_status_and_soc_frames_are_decoded(self):
    self.motor._can.frames = [
      ((9 << 8) | 10, True, False, b'\xff\xfe\x1d\xc0\xff\x85'),
      ((16 << 8) | 10, True, False, b'\x00\xfa\x01\x3b\xff\x85'),
      ((27 << 8) | 10, True, False, b'\x00\x00\x00\x00\x02\x1c'),
      ((99 << 8) | 10, True, False, b'\x03\x6c'),
    ]
    self.assertEqual(self.motor.update_motor_data(self.motor), 4)
    self.assertEqual(self.data.speed_erpm, -123456)
    self.assertEqual(self.data.motor_current_x10, -123)
    self.assertEqual(self.data.battery_current_x10, -123)
    self.assertEqual(self.data.battery_voltage_x10, 540)
    self.assertEqual(self.data.battery_soc_x1000, 876)
  def test_private_precision_frame_is_ignored(self):
    self.motor._can.frames = [((101 << 8) | 10, True, False,
                               b'\x00\x53\x01\xa7\x01\x8e\x04\x03')]
    self.assertEqual(self.motor.update_motor_data(self.motor), 1)
    self.assertEqual(self.data.battery_voltage_x10, 0)


if __name__ == '__main__':
  unittest.main()
