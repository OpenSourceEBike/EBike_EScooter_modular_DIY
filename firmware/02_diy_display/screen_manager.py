import time
import common.config_runtime as cfg
from screens.boot import BootScreen

# Lightweight "enum" that works on MicroPython
class ScreenID:
  BOOT      = 0
  MAIN      = 1
  CHARGING  = 2
  POWEROFF  = 3

class ScreenManager:
  def __init__(self, fb, vars):
    self.fb = fb

    self._screen_specs = {
      ScreenID.BOOT: ("screens.boot", "BootScreen"),
      ScreenID.MAIN: ("screens.main", "MainScreen"),
      ScreenID.CHARGING: ("screens.charging", "ChargingScreen"),
      ScreenID.POWEROFF: ("screens.poweroff", "PowerOffScreen"),
    }
    self._screen_factories = {
      ScreenID.BOOT: BootScreen,
    }
    self._screens = {}

    # Start in BOOT
    self._current_id = ScreenID.BOOT
    self._current = self._get_screen(self._current_id)
    self._current.on_enter()

    self._button_power_long_click_previous = False
    self._button_power_click_previous = False
    self._charging_state_previous = False
    self._charging_entry_is_auto = False

  # ---- Convenience getters ----
  def get_current_id(self):
    """Return the numeric ScreenID (fast, no strings)."""
    return self._current_id

  def get_current(self):
    """Return the current screen instance if you need to call methods."""
    return self._current

  def current_is(self, screen_id):
    """Fast equality without tuples/strings."""
    return self._current_id == screen_id

  def _get_screen(self, screen_id):
    screen = self._screens.get(screen_id)
    if screen is None:
      start_ms = time.ticks_ms()
      screen_factory = self._screen_factories.get(screen_id)
      if screen_factory is None:
        screen_factory = self._load_screen_factory(screen_id)
      screen = screen_factory(self.fb)
      self._screens[screen_id] = screen
      if cfg.boot_timing_debug:
        elapsed_ms = time.ticks_diff(time.ticks_ms(), start_ms)
        print("[boot screen +{:>4} ms] create id={}".format(elapsed_ms, screen_id))
    return screen

  def _load_screen_factory(self, screen_id):
    module_name, class_name = self._screen_specs[screen_id]
    module = __import__(module_name, None, None, (class_name,))
    screen_factory = getattr(module, class_name)
    self._screen_factories[screen_id] = screen_factory
    return screen_factory

  def preload(self, screen_id):
    if screen_id == self._current_id:
      return self._current
    return self._get_screen(screen_id)
    

  # ---- Core operations ----
  def render(self, vars):
    self._current.render(vars)
    try:
      self.fb.show()
    except Exception:
      pass

  def force(self, screen_id):
    """Switch to a screen by numeric ID (no strings!)."""
    if screen_id == self._current_id:
      return
    if cfg.boot_timing_debug:
      print("[screen] switch {} -> {}".format(self._current_id, screen_id))
    self._current.on_exit()
    self._current_id = screen_id
    self._current = self._get_screen(screen_id)
    self._current.on_enter()

  def update(self, vars):
    
    button_power_click = bool(vars.buttons_state & 0x0100)
    button_power_long_click = bool(vars.buttons_state & 0x0200)
    is_charging = vars.battery_is_charging
    wheel_stopped = (vars.wheel_speed_x10 == 0)
    brakes_on = bool(vars.brakes_are_active)

    # If Charging state changed
    if is_charging != self._charging_state_previous:
      self._charging_state_previous = is_charging
      
      # If is now Charging and not in Charging screen, go to Charging screen
      if is_charging and \
        not self.current_is(ScreenID.CHARGING):
        self._charging_entry_is_auto = True
        vars.motor_enable_state = False
        self.force(ScreenID.CHARGING)
        return

      # Charging entered automatically must also exit automatically.
      if not is_charging and \
        self.current_is(ScreenID.CHARGING) and \
        self._charging_entry_is_auto:
        self._charging_entry_is_auto = False
        vars.motor_enable_state = False
        self.force(ScreenID.BOOT)
        return

    # Click: Boot -> Main
    if self._button_power_click_previous != button_power_click:
      self._button_power_click_previous = button_power_click

      # We are in Boot scren, so go to Main screen
      if self.current_is(ScreenID.BOOT):
        self._charging_entry_is_auto = False
        vars.motor_enable_state = True
        self.force(ScreenID.MAIN)
        return
      
      # Go to Charging
      if (self.current_is(ScreenID.BOOT) or \
        self.current_is(ScreenID.MAIN)) and \
        wheel_stopped and \
        brakes_on:
        self._charging_entry_is_auto = False
        vars.motor_enable_state = False
        self.force(ScreenID.CHARGING)
        return

      # Charging entered manually may also be left manually.
      if self.current_is(ScreenID.CHARGING) and \
              not is_charging and \
              not self._charging_entry_is_auto:
        self._charging_entry_is_auto = False
        vars.motor_enable_state = False
        self.force(ScreenID.BOOT)
        return

      # We are in Power off screen, so restart the display
      elif self.current_is(ScreenID.POWEROFF):
        import machine
        machine.reset()
        return

    # Long click transitions
    if self._button_power_long_click_previous != button_power_long_click:
      self._button_power_long_click_previous = button_power_long_click

      # Go to Power off when stopped, or allow a brake-assisted shutdown while rolling.
      if self.current_is(ScreenID.MAIN) and (wheel_stopped or brakes_on):
        vars.motor_enable_state = False
        vars.shutdown_request = True
        self.force(ScreenID.POWEROFF)
        return
