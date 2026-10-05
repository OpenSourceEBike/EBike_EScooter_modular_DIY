import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
TEXT_BOX_PATH = ROOT / '02_diy_display' / 'widgets' / 'widget_text_box.py'
LCD_PATH = ROOT / '02_diy_display' / 'lcd' / 'lcd_st7565.py'


class _FakeFrameBuffer:
  def __init__(self, *args):
    self.args = args

  def fill(self, *args):
    return None

  def fill_rect(self, *args):
    return None

  def rect(self, *args):
    return None

  def pixel(self, *args):
    return None

  def blit(self, *args):
    return None


class _FakeScreenFrameBuffer:
  def __init__(self):
    self.blit_count = 0

  def fill_rect(self, *args):
    pass

  def rect(self, *args):
    pass

  def blit(self, *args):
    self.blit_count += 1


class _FakeFont:
  @staticmethod
  def get_ch(character):
    return b'\x80', 1, 1

  @staticmethod
  def height():
    return 1

  @staticmethod
  def max_width():
    return 1


class _FakeWriter:
  def __init__(self, *args, **kwargs):
    self.map = 0

  def set_clip(self, **kwargs):
    pass

  def set_vclip(self, *args):
    pass


class _FakePin:
  OUT = 1

  def __init__(self, *args, **kwargs):
    pass

  def init(self, *args, **kwargs):
    pass

  def __call__(self, *args):
    pass


class _FakeSpi:
  def __init__(self):
    self.writes = []

  def write(self, data):
    self.writes.append(data)


class _FakePwm:
  def __init__(self, *args):
    pass

  def freq(self, *args):
    pass

  def duty_u16(self, *args):
    pass


class _FakeTime:
  @staticmethod
  def sleep_ms(*args):
    pass


def _load_text_box():
  framebuf = types.ModuleType('framebuf')
  framebuf.FrameBuffer = _FakeFrameBuffer
  framebuf.MONO_VLSB = 0
  lcd = types.ModuleType('lcd')
  writer = types.ModuleType('lcd.writer')
  writer.Writer = _FakeWriter
  spec = importlib.util.spec_from_file_location(
    'widget_text_box_optimization_test_module', TEXT_BOX_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'framebuf': framebuf,
      'lcd': lcd,
      'lcd.writer': writer,
  }):
    spec.loader.exec_module(module)
  return module


def _load_lcd():
  framebuf = types.ModuleType('framebuf')
  framebuf.FrameBuffer = _FakeFrameBuffer
  framebuf.MONO_VLSB = 0
  machine = types.ModuleType('machine')
  machine.Pin = _FakePin
  machine.SPI = _FakeSpi
  machine.PWM = _FakePwm
  spec = importlib.util.spec_from_file_location(
    'lcd_st7565_optimization_test_module', LCD_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'framebuf': framebuf,
      'machine': machine,
  }):
    spec.loader.exec_module(module)
  module.time = _FakeTime
  return module


class DisplayRenderOptimizationTests(unittest.TestCase):
  def test_text_widget_skips_unchanged_content_but_redraws_after_layout_change(self):
    module = _load_text_box()
    fb = _FakeScreenFrameBuffer()
    widget = module.WidgetTextBox(fb, 16, 8, font=_FakeFont())
    widget.set_box(0, 0, 7, 7)

    self.assertTrue(widget.update('A'))
    self.assertEqual(fb.blit_count, 1)
    self.assertFalse(widget.update('A'))
    self.assertEqual(fb.blit_count, 1)

    widget.set_content_offset(dx=1)
    self.assertTrue(widget.update('A'))
    self.assertEqual(fb.blit_count, 2)

    widget.set_invert(True)
    self.assertTrue(widget.update('A'))
    self.assertEqual(fb.blit_count, 3)

  def test_lcd_flushes_only_after_a_framebuffer_mutation(self):
    module = _load_lcd()
    spi = _FakeSpi()
    display = module.ST7565(
      spi, _FakePin(), _FakePin(), _FakePin(), width=8, height=8)

    self.assertTrue(display.show())
    writes_after_first_flush = len(spi.writes)
    self.assertFalse(display.show())
    self.assertEqual(len(spi.writes), writes_after_first_flush)

    display.fill(0)
    self.assertTrue(display.show())
    self.assertGreater(len(spi.writes), writes_after_first_flush)


if __name__ == '__main__':
  unittest.main()
