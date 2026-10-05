import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = pathlib.Path(__file__).parents[1]
SCREEN_MANAGER_PATH = ROOT / '02_diy_display' / 'screen_manager.py'


class _FakeTime:
  @staticmethod
  def ticks_ms():
    return 1000

  @staticmethod
  def ticks_add(value, delta):
    return value + delta

  @staticmethod
  def ticks_diff(left, right):
    return left - right


class _FakeScreen:
  def __init__(self, fb):
    self.fb = fb

  def on_enter(self):
    pass

  def on_exit(self):
    pass

  def render(self, vars):
    pass


def _load_screen_manager():
  config = types.ModuleType('common.config_runtime')
  config.boot_timing_debug = False
  screens = types.ModuleType('screens')
  screens.__path__ = []
  boot = types.ModuleType('screens.boot')
  boot.BootScreen = _FakeScreen
  module_name = 'screen_manager_navigation_test_module'
  spec = importlib.util.spec_from_file_location(module_name, SCREEN_MANAGER_PATH)
  module = importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules, {
      'common.config_runtime': config,
      'screens': screens,
      'screens.boot': boot,
  }):
    spec.loader.exec_module(module)
  module.time = _FakeTime
  module.ScreenManager._load_screen_factory = lambda self, screen_id: _FakeScreen
  return module


class MainNavigationTests(unittest.TestCase):
  def state(self):
    return SimpleNamespace(
      buttons_state=0,
      power_click_pending=False,
      power_long_click_pending=False,
      charging_reconfirm_failed=False,
      rtc_sync_pending=False,
      comms_paused=False,
      charging_reconfirm_pending=False,
      motor_throttle_rearm_required=False,
      throttle_is_active=False,
      battery_is_charging=False,
      wheel_speed_x10=0,
      wheel_speed_telemetry_valid=True,
      brakes_are_active=False,
      motor_enable_state=False,
      shutdown_request=False,
    )

  def test_main_after_ready_gate_and_stopped_power_off(self):
    module = _load_screen_manager()
    state = self.state()
    manager = module.ScreenManager(object(), state)

    self.assertEqual(
      manager.get_current_id(), module.ScreenID.BOOT)
    self.assertFalse(state.motor_enable_state)

    # A short click does not leave the Ready safety gate.
    state.buttons_state = 0x0100
    state.power_click_pending = True
    manager.update(state)
    self.assertEqual(manager.get_current_id(), module.ScreenID.BOOT)
    self.assertFalse(state.motor_enable_state)

    # A long press arms the motor and opens the riding dashboard.
    state.buttons_state = 0x0200
    state.power_long_click_pending = True
    manager.update(state)
    self.assertEqual(
      manager.get_current_id(), module.ScreenID.MAIN)
    self.assertTrue(state.motor_enable_state)

    # The normal dashboard keeps the stopped-only power-off gesture.
    state.buttons_state = 0x0300
    state.power_long_click_pending = True
    manager.update(state)
    self.assertEqual(manager.get_current_id(), module.ScreenID.POWEROFF)
    self.assertFalse(state.motor_enable_state)
    self.assertTrue(state.shutdown_request)

  def test_braking_while_moving_does_not_power_off(self):
    module = _load_screen_manager()
    state = self.state()
    manager = module.ScreenManager(object(), state)
    manager.force(module.ScreenID.MAIN)
    state.wheel_speed_x10 = 120
    state.brakes_are_active = True
    state.buttons_state = 0x0300
    state.power_long_click_pending = True

    manager.update(state)

    self.assertEqual(
      manager.get_current_id(), module.ScreenID.MAIN)
    self.assertFalse(state.shutdown_request)

  def test_stale_zero_speed_does_not_power_off(self):
    module = _load_screen_manager()
    state = self.state()
    manager = module.ScreenManager(object(), state)
    manager.force(module.ScreenID.MAIN)
    state.wheel_speed_telemetry_valid = False
    state.brakes_are_active = True
    state.buttons_state = 0x0300
    state.power_long_click_pending = True

    manager.update(state)

    self.assertEqual(
      manager.get_current_id(), module.ScreenID.MAIN)
    self.assertFalse(state.shutdown_request)

  def test_ready_long_press_with_brakes_enters_manual_charging(self):
    module = _load_screen_manager()
    state = self.state()
    state.brakes_are_active = True
    manager = module.ScreenManager(object(), state)
    state.buttons_state = 0x0200
    state.power_long_click_pending = True

    manager.update(state)

    self.assertEqual(manager.get_current_id(), module.ScreenID.CHARGING)
    self.assertFalse(state.motor_enable_state)

  def test_manual_charging_returns_to_ready(self):
    module = _load_screen_manager()
    state = self.state()
    manager = module.ScreenManager(object(), state)
    manager.force(module.ScreenID.CHARGING)
    manager._charging_entry_is_auto = False
    state.buttons_state = 0x0100
    state.power_click_pending = True
    manager.update(state)
    self.assertEqual(manager.get_current_id(), module.ScreenID.BOOT)
    self.assertFalse(state.motor_enable_state)


if __name__ == '__main__':
  unittest.main()
