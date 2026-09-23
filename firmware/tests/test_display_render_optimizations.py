import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
TEXT_BOX_PATH = ROOT / '02_diy_display' / 'widgets' / 'widget_text_box.py'
LCD_PATH = ROOT / '02_diy_display' / 'lcd' / 'lcd_st7565.py'
RESISTANCE_SCREEN_PATH = ROOT / '02_diy_display' / 'screens' / 'battery_resistance.py'


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


def _load_resistance_screen():
  class FakeBaseScreen:
    def __init__(self, fb):
      self.fb = fb

    def clear(self):
      pass

  class FakeTextBox:
    instances = []

    def __init__(self, *args, **kwargs):
      self.updates = []
      FakeTextBox.instances.append(self)

    def set_box(self, **kwargs):
      pass

    def update(self, text):
      self.updates.append(text)

  screens = types.ModuleType('screens')
  screens.__path__ = []
  base = types.ModuleType('screens.base')
  base.BaseScreen = FakeBaseScreen
  widgets = types.ModuleType('widgets')
  widgets.__path__ = []
  text_box = types.ModuleType('widgets.widget_text_box')
  text_box.WidgetTextBox = FakeTextBox
  fonts = types.ModuleType('fonts')
  fonts.__path__ = []
  font_small = types.ModuleType('fonts.robotobold12')
  font_current = types.ModuleType('fonts.robotobold18')
  spec = importlib.util.spec_from_file_location(
    'screens.battery_resistance_cache_test_module', RESISTANCE_SCREEN_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'screens': screens,
      'screens.base': base,
      'widgets': widgets,
      'widgets.widget_text_box': text_box,
      'fonts': fonts,
      'fonts.robotobold12': font_small,
      'fonts.robotobold18': font_current,
  }):
    spec.loader.exec_module(module)
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

  def test_resistance_screens_format_only_changed_values(self):
    module = _load_resistance_screen()
    vars = types.SimpleNamespace(
      battery_resistance_config_error='',
      battery_resistance_last_mohm=35,
      battery_resistance_state=1,
      battery_resistance_state_samples=1,
      battery_resistance_state_samples_required=3,
      battery_resistance_history_dirty=False,
      battery_resistance_state_seconds=2,
      battery_resistance_min_mohm=31,
      battery_resistance_min_timestamp=0,
      battery_resistance_max_mohm=40,
      battery_resistance_max_timestamp=0,
    )

    dashboard = module.BatteryResistanceScreen(types.SimpleNamespace(width=64))
    self.assertEqual(module.BatteryResistanceScreen.__bases__,
                     (module.BaseScreen,))
    dashboard.on_enter()
    dashboard.render(vars)
    self.assertEqual(dashboard._resistance.updates[-1], '35 mOhm')
    self.assertEqual(dashboard._state.updates[-1], 'STATE: SETTLE')
    self.assertEqual(dashboard._samples.updates[-1], 'SAMPLES: 1/3')
    self.assertEqual(dashboard._range.updates[-1], 'MIN 31  MAX 40 mOhm')
    first_dashboard_updates = len(dashboard._samples.updates)
    dashboard.render(vars)
    self.assertEqual(len(dashboard._samples.updates), first_dashboard_updates)
    vars.battery_resistance_state_samples = 2
    dashboard.render(vars)
    self.assertEqual(len(dashboard._samples.updates),
                     first_dashboard_updates + 1)
    self.assertEqual(dashboard._samples.updates[-1], 'SAMPLES: 2/3')
    vars.battery_resistance_state = 3
    dashboard.render(vars)
    self.assertEqual(dashboard._state.updates[-1], 'STATE: COMPLETE')
    self.assertEqual(dashboard._samples.updates[-1], '')
    vars.battery_resistance_config_error = 'invalid config'
    dashboard.render(vars)
    self.assertEqual(dashboard._resistance.updates[-1], 'CONFIG ERR')
    self.assertEqual(dashboard._state.updates[-1], 'STATE: CONFIG ERR')
    vars.battery_resistance_config_error = ''
    vars.battery_resistance_state = -1
    dashboard.render(vars)
    self.assertEqual(dashboard._state.updates[-1], 'STATE: WAIT BMS')
    vars.battery_resistance_state = 0
    vars.battery_resistance_state_samples = 2
    dashboard.render(vars)
    self.assertEqual(dashboard._state.updates[-1], 'STATE: REFERENCE')
    self.assertEqual(dashboard._samples.updates[-1], 'BASELINE: 2/3')
    vars.battery_resistance_state_samples = 3
    dashboard.render(vars)
    self.assertEqual(dashboard._state.updates[-1], 'STATE: WAIT LOAD')
    self.assertEqual(dashboard._samples.updates[-1], 'BASELINE: 3/3')

    history = module.BatteryResistanceHistoryScreen(types.SimpleNamespace(width=64))
    history.on_enter()
    history.render(vars)
    first_history_updates = (
      len(history._title.updates), len(history._current.updates),
      len(history._state.updates), len(history._minimum.updates),
      len(history._maximum.updates))
    history.render(vars)
    self.assertEqual((
      len(history._title.updates), len(history._current.updates),
      len(history._state.updates), len(history._minimum.updates),
      len(history._maximum.updates)), first_history_updates)
    vars.battery_resistance_max_mohm = 41
    history.render(vars)
    self.assertEqual(len(history._maximum.updates), first_history_updates[4] + 1)
    self.assertEqual(len(history._minimum.updates), first_history_updates[3])


if __name__ == '__main__':
  unittest.main()
