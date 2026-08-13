import time
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small
from fonts import robotobold18 as font_current


class BatteryResistanceScreen(BaseScreen):
  NAME = "BatteryResistance"

  def __init__(self, fb):
    super().__init__(fb)

  def on_enter(self):
    self.clear()
    self._title = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside="center"
    )
    self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=11)
    self._title.update("Battery resistance")
    self._current = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_current, align_inside="center"
    )
    self._current.set_box(x1=0, y1=13, x2=self.fb.width - 1, y2=30)
    self._current.update("na")
    self._current_timestamp = self._make_line(31, "center")
    self._minimum = self._make_line(43, "center")
    self._maximum = self._make_line(54, "center")

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

  def render(self, vars):
    last_value = vars.battery_resistance_last_mohm
    if getattr(vars, 'battery_resistance_config_error', ''):
      self._title.update("Resist config err")
    elif last_value is None:
      self._title.update("Battery resistance")
    elif getattr(vars, 'battery_resistance_history_dirty', False):
      self._title.update("THIS BOOT")
    else:
      self._title.update("LAST SAVED")
    self._current.update(
      "{} mOhm".format(last_value) if last_value is not None else "na"
    )
    self._current_timestamp.update(
      self._timestamp(vars.battery_resistance_last_timestamp)
    )
    self._minimum.update(self._format_history(
      "Min", vars.battery_resistance_min_mohm,
      vars.battery_resistance_min_timestamp
    ))
    self._maximum.update(self._format_history(
      "Max", vars.battery_resistance_max_mohm,
      vars.battery_resistance_max_timestamp
    ))
