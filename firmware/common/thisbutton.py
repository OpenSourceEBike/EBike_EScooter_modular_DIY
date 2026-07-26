import time
from machine import Pin

def _ticks_us():
  # Use a clock supported by ticks_diff on all target MicroPython ports.
  try:
    return time.ticks_us()
  except AttributeError:
    return time.ticks_ms() * 1000


def _ticks_diff(now, previous):
  """Return elapsed time using MicroPython's wrap-safe tick arithmetic."""
  try:
    return time.ticks_diff(now, previous)
  except AttributeError:
    return now - previous


def _ticks_add(now, delta):
  try:
    return time.ticks_add(now, delta)
  except AttributeError:
    return now + delta

class thisButton:
  def __init__(self, gpio, pull_up=True):
    # gpio can be an int (pin number) or a Pin object
    self.pin = gpio if isinstance(gpio, Pin) else Pin(gpio, Pin.IN)
    # configure pull
    try:
      self.pin.init(Pin.IN, Pin.PULL_UP if pull_up else Pin.PULL_DOWN)
    except (AttributeError, ValueError):
      # Some MCUs might lack PULL_DOWN; if so, leave floating and expect external pull
      self.pin.init(Pin.IN)

    self.prev_state = None
    self.cur_state = None
    # active state = low when pull_up (pressed ties to GND), else high
    self.activated_state = 0 if pull_up else 1

    self.cur_time = None
    self.prev_state_change = None
    self.active = False
    self.long_press_activated = False
    self.debounce_start = 0
    self.debouncing = False
    self.held = False

    self.click_start_function = None
    self.click_release_function = None
    self.long_press_start_function = None
    self.long_press_release_function = None
    self.held_function = None
    self.click_only_assigned = False
    self.switch_mode = False
    self.switch_change_function = None
    self.switch_initialized = False
    self._candidate_state = None
    self._stable_state = None
    self._candidate_change_time = None

    # Thresholds use ticks_us units: debounce, minimum click, long press,
    # held repeat.
    self.default_debounce_threshold = 5_000
    self.default_click_min_threshold = 100_000
    self.default_long_press_threshold = 1_000_000
    self.default_held_interval = 100_000

    self.debounce_threshold = self.default_debounce_threshold
    self.click_min_threshold = self.default_click_min_threshold
    self.long_press_threshold = self.default_long_press_threshold
    self.held_interval = self.default_held_interval
    self.held_next_time = 0

    self.debug = False

  # this needs to be called frequently from the main loop
  def tick(self):
    self.cur_time = _ticks_us()

    if self.switch_mode:
      self._tick_switch()
      return

    raw_state = 1 if self.pin.value() else 0
    state_changed = False

    # Keep a candidate separate from the last accepted state. A transition is
    # processed only after the candidate remains stable for the debounce time.
    if self._candidate_state is None:
      self._candidate_state = raw_state
      self.cur_state = raw_state
      self.debounce_start = self.cur_time
      self._candidate_change_time = self.cur_time
      self.debouncing = self.debounce_threshold > 0
      if self.debouncing:
        return
      self._stable_state = raw_state
      state_changed = True
    elif raw_state != self._candidate_state:
      self._candidate_state = raw_state
      self.cur_state = raw_state
      self.debounce_start = self.cur_time
      self._candidate_change_time = self.cur_time
      self.debouncing = self.debounce_threshold > 0
      if self.debouncing:
        return
      self._stable_state = raw_state
      state_changed = True
    elif self.debouncing:
      if _ticks_diff(self.cur_time, self.debounce_start) < self.debounce_threshold:
        return
      self.debouncing = False
      if self._stable_state != self._candidate_state:
        self._stable_state = self._candidate_state
        state_changed = True

    self.cur_state = self._stable_state
    if self.prev_state is None and self._stable_state is not None:
      state_changed = True

    if self.cur_state == self.activated_state:
      # button is active this cycle
      if self.active is not True:
        # just pressed
        self.active = True
        self.prev_state_change = (
          self._candidate_change_time
          if self._candidate_change_time is not None else self.cur_time
        )
        if self.debug:
          print("Click Down")
      else:
        # still held
        if _ticks_diff(self.cur_time, self.prev_state_change) >= self.long_press_threshold:
          # Long-press start
          if self.long_press_activated is not True:
            if self.debug:
              print("Long press start Detected")
            self.long_press_activated = True
            if self.long_press_start_function is not None:
              try:
                self.long_press_start_function()
              except Exception as e:
                if self.debug: print("long_press_start error:", e)
          # Held repeat
          elif self.held_function is not None:
            self.long_press_activated = True
            if not self.held:
              self.held = True
              try:
                self.held_function()
              except Exception as e:
                if self.debug: print("held first error:", e)
              self.held_next_time = _ticks_add(self.cur_time, self.held_interval)
            elif _ticks_diff(self.cur_time, self.held_next_time) >= 0:
              try:
                self.held_function()
              except Exception as e:
                if self.debug: print("held repeat error:", e)
              self.held_next_time = _ticks_add(self.cur_time, self.held_interval)

    # button released (and not bouncing)
    elif (self.cur_state != self.activated_state) and (self.active is True):
      release_time = (
        self._candidate_change_time
        if self._candidate_change_time is not None else self.cur_time
      )
      press_duration = _ticks_diff(release_time, self.prev_state_change)
      if (self.long_press_activated or
          press_duration >= self.long_press_threshold):
        # long press / held release
        if not self.long_press_activated:
          # The loop may have been delayed past the threshold; classify the
          # press correctly even if no tick occurred while it was held.
          self.long_press_activated = True
          if self.long_press_start_function is not None:
            try:
              self.long_press_start_function()
            except Exception as e:
              if self.debug: print("long_press_start error:", e)
        self.long_press_activated = False
        self.active = False
        self.held = False
        if self.long_press_release_function is not None:
          try:
            self.long_press_release_function()
          except Exception as e:
            if self.debug: print("long_press_release error:", e)
        if self.debug:
          print("Long press or hold duration:", press_duration)
      else:
        # click release
        self.active = False
        if (press_duration >= self.click_min_threshold and
            press_duration < self.long_press_threshold):
          if self.click_start_function is not None:
            try:
              self.click_start_function()
            except Exception as e:
              if self.debug: print("click_start error:", e)
          if self.click_release_function is not None:
            try:
              self.click_release_function()
            except Exception as e:
              if self.debug: print("click_release error:", e)
        if self.debug:
          print("Click release, duration:", press_duration)

    if state_changed:
      self.prev_state = self.cur_state

  def _tick_switch(self):
    """Poll a maintained switch and notify only after a stable change."""
    raw_state = 1 if self.pin.value() else 0
    if self.cur_state is None or raw_state != self.cur_state:
      self.cur_state = raw_state
      self.debounce_start = self.cur_time
      self.debouncing = True
      return

    if self.debouncing:
      if _ticks_diff(self.cur_time, self.debounce_start) < self.debounce_threshold:
        return
      # The candidate remained unchanged for the full debounce interval.
      self.debouncing = False

    new_active = self.cur_state == self.activated_state
    if self.switch_initialized and new_active == self.active:
      return

    self.active = new_active
    self.prev_state_change = self.cur_time
    self.switch_initialized = True
    if self.switch_change_function is not None:
      try:
        self.switch_change_function(self.active)
      except Exception as e:
        if self.debug: print("switch change error:", e)

  # ----- utils -----
  def msToNs(self, milliseconds):
    return int(milliseconds) * 1_000

  def nsToMs(self, nanoseconds):
    return nanoseconds / 1_000.0

  def start_debounce(self):
    self.debouncing = True
    self.debounce_start = self.cur_time

  # ----- callback registration -----
  def assignClickStart(self, function_name):
    self.click_start_function = function_name
    if (self.long_press_start_function is None and
      self.long_press_release_function is None and
      self.held_function is None):
      self.click_only_assigned = True

  def assignClickRelease(self, function_name):
    self.click_release_function = function_name

  def assignLongClickStart(self, function_name):
    self.long_press_start_function = function_name
    self.click_only_assigned = False

  def assignLongClickRelease(self, function_name):
    self.long_press_release_function = function_name
    self.click_only_assigned = False

  def assignHeld(self, function_name, milliseconds=-1):
    self.held_function = function_name
    self.click_only_assigned = False
    if milliseconds < 0:
      self.held_interval = self.default_held_interval
    else:
      self.held_interval = self.msToNs(milliseconds)

  # ----- configuration -----
  def toggleDebug(self):
    self.debug = not self.debug

  def setDebounceThreshold(self, milliseconds=-1):
    self.debounce_threshold = (
      self.default_debounce_threshold if milliseconds < 0 else self.msToNs(milliseconds)
    )

  def setClickMinThreshold(self, milliseconds=-1):
    self.click_min_threshold = (
      self.default_click_min_threshold if milliseconds < 0 else self.msToNs(milliseconds)
    )

  def setSwitchMode(self, enabled=True):
    self.switch_mode = bool(enabled)
    self.switch_initialized = False
    self.debouncing = False
    self._candidate_state = None
    self._stable_state = None
    self._candidate_change_time = None

  def assignSwitchChange(self, function_name):
    self.switch_change_function = function_name

  def setLongPressThreshold(self, milliseconds=-1):
    self.long_press_threshold = (
      self.default_long_press_threshold if milliseconds < 0 else self.msToNs(milliseconds)
    )

  def setHeldInterval(self, milliseconds=-1):
    self.held_interval = (
      self.default_held_interval if milliseconds < 0 else self.msToNs(milliseconds)
    )

  # ----- properties -----
  @property
  def isHeld(self):
    # True if a long press or hold is active
    return self.long_press_activated

  @property
  def heldDuration(self):
    # ms held (0 if not in long-press/hold)
    if self.long_press_activated:
      return self.nsToMs(_ticks_diff(_ticks_us(), self.prev_state_change))
    return 0

  @property
  def gpio_state(self):
    # deprecated alias (kept for compatibility)
    return 1 if self.pin.value() else 0

  @property
  def gpioState(self):
    return 1 if self.pin.value() else 0

  @property
  def buttonActive(self):
    # True while the button is currently pressed after debouncing.
    return bool(self.active)
