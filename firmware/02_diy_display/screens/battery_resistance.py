import time
from .base import BaseScreen
from .main import MainScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small
from fonts import robotobold18 as font_current

RESISTANCE_STATE_LABELS = (
  "REFERENCE",
  "SETTLE",
  "LOAD",
  "COMPLETE",
)


RESISTANCE_STATE_SHORT_LABELS = (
  "R", "S", "L", "OK",
)


class BatteryResistanceScreen(MainScreen):
  NAME = "BatteryResistance"

  def on_enter(self):
    # Retain speed, SOC, lights, brakes, thermal bars and warning handling from
    # MainScreen. The compact resistance readout replaces part of the power
    # graphic, making this a real MAIN replacement rather than a safety mode.
    super().on_enter()
    self._resistance = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside="center"
    )
    self._resistance.set_box(x1=1, y1=19, x2=62, y2=30)
    self._resistance.update("B --")

  def render(self, vars):
    super().render(vars)
    if getattr(vars, 'battery_resistance_config_error', ''):
      text = "B ERR"
    else:
      value = getattr(vars, 'battery_resistance_last_mohm', None)
      state = getattr(vars, 'battery_resistance_state', -1)
      samples = max(0, int(getattr(
        vars, 'battery_resistance_state_samples', 0)))
      required_samples = max(0, int(getattr(
        vars, 'battery_resistance_state_samples_required', 0)))
      state_index = -1
      try:
        state_index = int(state)
        if state_index < 0:
          raise ValueError
        state_text = RESISTANCE_STATE_SHORT_LABELS[state_index]
      except (IndexError, TypeError, ValueError):
        state_text = "--"
      value_text = "--" if value is None else str(int(value))
      if required_samples and state_index != 3:
        state_text = "{}{}/{}".format(
          state_text, min(samples, required_samples), required_samples)
      text = "{}m {}".format(value_text, state_text)
    self._resistance.update(text)


class BatteryResistanceHistoryScreen(BaseScreen):
  NAME = "BatteryResistanceHistory"

  def __init__(self, fb):
    super().__init__(fb)

  def on_enter(self):
    self.clear()
    self._title = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside="center"
    )
    self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=11)
    self._title.update("BMS resistance")
    self._current = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_current, align_inside="center"
    )
    self._current.set_box(x1=0, y1=13, x2=self.fb.width - 1, y2=30)
    self._current.update("na")
    self._state = self._make_line(31, "center")
    self._minimum = self._make_line(43, "center")
    self._maximum = self._make_line(53, "center")

  def _make_line(self, y, align_inside):
    line = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside=align_inside
    )
    line.set_box(x1=0, y1=y, x2=self.fb.width - 1, y2=y + 10)
    line.update("")
    return line

  def _timestamp(self, timestamp):
    if not timestamp:
      return "na"
    try:
      dt = time.localtime(timestamp)
      return "{:02}/{:02} {:02}:{:02}".format(dt[2], dt[1], dt[3], dt[4])
    except Exception:
      return "na"

  def _format_history(self, label, value, timestamp):
    if value is None:
      return "{}: na".format(label)
    return "{}: {}m {}".format(label, value, self._timestamp(timestamp))

  def _format_state(self, state, seconds):
    try:
      state = int(state)
      seconds = max(0, min(255, int(seconds)))
      label = RESISTANCE_STATE_LABELS[state]
    except (IndexError, TypeError, ValueError):
      return "STATE: na"
    if state < 0:
      return "STATE: na"
    return "{}: {}s".format(label, seconds)

  def render(self, vars):
    last_value = vars.battery_resistance_last_mohm
    if getattr(vars, 'battery_resistance_config_error', ''):
      self._title.update("BMS config err")
    elif last_value is None:
      self._title.update("BMS resistance")
    elif getattr(vars, 'battery_resistance_history_dirty', False):
      self._title.update("THIS BOOT")
    else:
      self._title.update("LAST SAVED")
    self._current.update(
      "{} mOhm".format(last_value) if last_value is not None else "na"
    )
    self._state.update(self._format_state(
      getattr(vars, 'battery_resistance_state', -1),
      getattr(vars, 'battery_resistance_state_seconds', 0),
    ))
    self._minimum.update(self._format_history(
      "Min", vars.battery_resistance_min_mohm,
      vars.battery_resistance_min_timestamp
    ))
    self._maximum.update(self._format_history(
      "Max", vars.battery_resistance_max_mohm,
      vars.battery_resistance_max_timestamp
    ))
