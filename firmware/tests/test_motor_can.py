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
    self.original_ticks_ms = getattr(time, 'ticks_ms', None)
    time.sleep_ms = self.sleep_calls.append
    time.ticks_ms = lambda: 1234
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
    if self.original_ticks_ms is None:
      del time.ticks_ms
    else:
      time.ticks_ms = self.original_ticks_ms

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

  def test_precision_battery_frame_is_decoded_atomically(self):
    # Command 101: 54.000 V, 123.456 A, in uint32 mV and int32 mA.
    self.motor._can.frames = [
      ((101 << 8) | 10, True, False,
       b'\x00\x00\xd2\xf0\x00\x01\xe2\x40')
    ]
    self.assertEqual(self.motor.update_motor_data(self.motor), 1)
    self.assertEqual(self.data.battery_voltage_measurement_x1000, 54000)
    self.assertEqual(self.data.battery_current_measurement_x1000, 123456)
    self.assertEqual(self.data.battery_precision_last_update_ms, 1234)
    self.assertEqual(self.data.battery_precision_update_counter, 1)

  def test_standard_status_frames_are_ignored(self):
    self.motor._can.frames = [
      ((9 << 8) | 10, True, False, b'\x00\x00\x04\xd2\x00\x7b'),
      ((16 << 8) | 10, True, False, b'\x00\x19\x00\x1a\x00\x7b'),
      ((27 << 8) | 10, True, False, b'\x00\x00\x00\x00\x02\x14'),
      ((100 << 8) | 10, True, False, b'\x03\x6c'),
    ]
    self.assertEqual(self.motor.update_motor_data(self.motor), 4)
    self.assertEqual(self.data.battery_current_x10, 0)
    self.assertEqual(self.data.battery_voltage_x10, 0)
    self.assertEqual(self.data.speed_erpm, 0)
    self.assertEqual(self.data.battery_soc_x1000, 0)
    self.assertEqual(self.data.last_can_data_ms, 0)

  def test_lisp_motion_and_thermal_frames_are_decoded(self):
    # Command 102: -123456 ERPM, -12.3 A motor current, sequence 7.
    # Command 103: 25.0 C VESC, 31.5 C motor, 87.6% SOC, sequence 8.
    self.motor._can.frames = [
      ((102 << 8) | 10, True, False,
       b'\xff\xfe\x1d\xc0\xff\x85\x07\x00'),
      ((103 << 8) | 10, True, False,
       b'\x00\xfa\x01\x3b\x03\x6c\x08\x00'),
    ]
    self.assertEqual(self.motor.update_motor_data(self.motor), 2)
    self.assertEqual(self.data.lisp_speed_erpm, -123456)
    self.assertEqual(self.data.lisp_motor_current_x10, -123)
    self.assertEqual(self.data.lisp_motion_sequence, 7)
    self.assertEqual(self.data.lisp_motion_last_update_ms, 1234)
    self.assertEqual(self.data.lisp_vesc_temperature_x10, 250)
    self.assertEqual(self.data.lisp_motor_temperature_x10, 315)
    self.assertEqual(self.data.lisp_battery_soc_x1000, 876)
    self.assertEqual(self.data.lisp_thermal_sequence, 8)
    self.assertEqual(self.data.lisp_thermal_last_update_ms, 1234)

  def test_lisp_sequence_gaps_are_counted_after_the_first_frame(self):
    self.motor._can.frames = [
      ((102 << 8) | 10, True, False,
       b'\x00\x00\x00\x01\x00\x01\x07\x00'),
      ((102 << 8) | 10, True, False,
       b'\x00\x00\x00\x02\x00\x01\x0a\x00'),
      ((103 << 8) | 10, True, False,
       b'\x00\xfa\x01\x3b\x03\x6c\x08\x00'),
      ((103 << 8) | 10, True, False,
       b'\x00\xfa\x01\x3b\x03\x6c\x0b\x00'),
    ]
    self.assertEqual(self.motor.update_motor_data(self.motor), 4)
    self.assertEqual(self.data.lisp_motion_loss_count, 2)
    self.assertEqual(self.data.lisp_thermal_loss_count, 2)


if __name__ == '__main__':
  unittest.main()
