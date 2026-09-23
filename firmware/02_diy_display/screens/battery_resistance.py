import time
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small
from fonts import robotobold18 as font_current

RESISTANCE_STATE_LABELS = (
  "REFERENCE",
  "SETTLE",
  "LOAD",
  "COMPLETE",
)


class BatteryResistanceScreen(BaseScreen):
  NAME = "BatteryResistance"

  def on_enter(self):
    self.clear()
    self._title = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside="center"
    )
    self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=11)
    self._title.update("BMS resistance")
    self._resistance = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_current, align_inside="center"
    )
    self._resistance.set_box(x1=0, y1=12, x2=self.fb.width - 1, y2=30)
    self._resistance.update("-- mOhm")
    self._state = self._make_line(31)
    self._samples = self._make_line(42)
    self._range = self._make_line(53)
    self._resistance_config_error_previous = None
    self._resistance_value_previous = None
    self._resistance_state_previous = None
    self._resistance_samples_previous = None
    self._resistance_required_samples_previous = None
    self._resistance_min_previous = -1
    self._resistance_max_previous = -1

  def _make_line(self, y):
    line = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small, align_inside="center"
    )
    line.set_box(x1=0, y1=y, x2=self.fb.width - 1, y2=y + 10)
    line.update("")
    return line

  def render(self, vars):
    # The current reading is visible here, so do not replay its alert later.
    if getattr(vars, 'battery_resistance_alert_pending', None) is not None:
      vars.battery_resistance_alert_pending = None
    config_error = getattr(vars, 'battery_resistance_config_error', '')
    value = getattr(vars, 'battery_resistance_last_mohm', None)
    state = getattr(vars, 'battery_resistance_state', -1)
    samples = max(0, int(getattr(
      vars, 'battery_resistance_state_samples', 0)))
    required_samples = max(0, int(getattr(
      vars, 'battery_resistance_state_samples_required', 0)))
    config_changed = config_error != self._resistance_config_error_previous
    if (config_changed or
        value != self._resistance_value_previous):
      self._resistance_config_error_previous = config_error
      self._resistance_value_previous = value
      if config_error:
        self._resistance.update("CONFIG ERR")
      else:
        self._resistance.update(
          "{} mOhm".format(value) if value is not None else "-- mOhm")

    state_changed = state != self._resistance_state_previous
    progress_changed = (
      samples != self._resistance_samples_previous or
      required_samples != self._resistance_required_samples_previous)
    if state_changed or config_changed or (state == 0 and progress_changed):
      self._resistance_state_previous = state
      if config_error:
        state_text = "CONFIG ERR"
      elif state == 0 and required_samples and samples >= required_samples:
        state_text = "WAIT LOAD"
      else:
        try:
          state_index = int(state)
          if state_index < 0:
            raise ValueError
          state_text = RESISTANCE_STATE_LABELS[state_index]
        except (IndexError, TypeError, ValueError):
          state_text = "WAIT BMS"
      self._state.update("STATE: {}".format(state_text))

    if progress_changed or state_changed or config_changed:
      self._resistance_samples_previous = samples
      self._resistance_required_samples_previous = required_samples
      progress_label = "BASELINE" if state == 0 else "SAMPLES"
      self._samples.update(
        "{}: {}/{}".format(progress_label,
                           min(samples, required_samples), required_samples)
        if required_samples and state != 3 and not config_error else "")

    minimum = getattr(vars, 'battery_resistance_min_mohm', None)
    maximum = getattr(vars, 'battery_resistance_max_mohm', None)
    if (minimum != self._resistance_min_previous or
        maximum != self._resistance_max_previous):
      self._resistance_min_previous = minimum
      self._resistance_max_previous = maximum
      self._range.update("MIN {}  MAX {} mOhm".format(
        "--" if minimum is None else minimum,
        "--" if maximum is None else maximum))


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
    self._title_key_previous = None
    self._current_value_previous = None
    self._state_value_previous = None
    self._state_seconds_previous = None
    self._minimum_value_previous = None
    self._minimum_timestamp_previous = None
    self._maximum_value_previous = None
    self._maximum_timestamp_previous = None

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
    config_error = getattr(vars, 'battery_resistance_config_error', '')
    history_dirty = bool(getattr(vars, 'battery_resistance_history_dirty', False))
    if config_error:
      title_key = 1
      title = "BMS config err"
    elif last_value is None:
      title_key = 2
      title = "BMS resistance"
    elif history_dirty:
      title_key = 3
      title = "THIS BOOT"
    else:
      title_key = 4
      title = "LAST SAVED"
    if title_key != self._title_key_previous:
      self._title_key_previous = title_key
      self._title.update(title)

    if last_value != self._current_value_previous:
      self._current_value_previous = last_value
      self._current.update(
        "{} mOhm".format(last_value) if last_value is not None else "na")

    state = getattr(vars, 'battery_resistance_state', -1)
    state_seconds = getattr(vars, 'battery_resistance_state_seconds', 0)
    if (state != self._state_value_previous or
        state_seconds != self._state_seconds_previous):
      self._state_value_previous = state
      self._state_seconds_previous = state_seconds
      self._state.update(self._format_state(state, state_seconds))

    minimum_value = vars.battery_resistance_min_mohm
    minimum_timestamp = vars.battery_resistance_min_timestamp
    if (minimum_value != self._minimum_value_previous or
        minimum_timestamp != self._minimum_timestamp_previous):
      self._minimum_value_previous = minimum_value
      self._minimum_timestamp_previous = minimum_timestamp
      self._minimum.update(self._format_history(
        "Min", minimum_value, minimum_timestamp))

    maximum_value = vars.battery_resistance_max_mohm
    maximum_timestamp = vars.battery_resistance_max_timestamp
    if (maximum_value != self._maximum_value_previous or
        maximum_timestamp != self._maximum_timestamp_previous):
      self._maximum_value_previous = maximum_value
      self._maximum_timestamp_previous = maximum_timestamp
      self._maximum.update(self._format_history(
        "Max", maximum_value, maximum_timestamp))
