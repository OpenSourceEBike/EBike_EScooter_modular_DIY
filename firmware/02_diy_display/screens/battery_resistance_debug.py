from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font


class BatteryResistanceDebugScreen(BaseScreen):
  """Temporary riding view for battery-resistance diagnostics."""

  NAME = "Battery resistance debug"
  _STATE_NAMES = {
    -1: "unavailable",
    0: "get reference",
    1: "ramp to load",
    2: "get load",
    3: "collect samples",
    4: "complete",
    5: "failed",
  }

  def __init__(self, fb):
    super().__init__(fb)
    self._lines = []
    self._line_texts = [None] * 5
    for index in range(5):
      line = WidgetTextBox(
        self.fb, self.fb.width, self.fb.width,
        font=font, align_inside="left"
      )
      y = index * 12
      line.set_box(x1=0, y1=y, x2=self.fb.width - 1, y2=y + 10)
      self._lines.append(line)

  def on_enter(self):
    self.clear()
    self._line_texts = [None] * len(self._lines)

  def _update_lines(self, texts):
    for index in range(len(self._lines)):
      text = texts[index]
      if text != self._line_texts[index]:
        self._line_texts[index] = text
        self._lines[index].update(text)

  def render(self, vars):
    # The debug view already exposes the completed result. Consume the normal
    # dashboard alert here so it is neither shown nor delayed until a later
    # return to MainScreen.
    if getattr(vars, "battery_resistance_alert_pending", None) is not None:
      vars.battery_resistance_alert_pending = None

    state = int(getattr(vars, "battery_resistance_debug_phase", -1))
    texts = [""] * 5
    texts[0] = "{}: {}".format(
      state, self._STATE_NAMES.get(state, "unknown"))
    error_count = int(getattr(
      vars, "battery_resistance_debug_error_count", 0))
    sample_count = int(getattr(
      vars, "battery_resistance_debug_sample_count", 0))
    reference_sample_count = int(getattr(
      vars, "battery_resistance_debug_reference_sample_count", 0))
    phase_elapsed_seconds = int(getattr(
      vars, "battery_resistance_debug_phase_elapsed_seconds", 0))
    result = getattr(vars, "battery_resistance_last_mohm", None)
    result = result if result is not None else "na"
    if getattr(vars, "motor_board_rx_ok", False):
      battery_voltage_x10 = int(getattr(vars, "battery_voltage_x10", 0))
      battery_current_x10 = int(getattr(vars, "battery_current_x10", 0))
      battery_power_w = int(
        (battery_voltage_x10 * battery_current_x10) / 100.0)
      power_text = "power: {:+d} W".format(battery_power_w)
    else:
      power_text = "power: na"

    if state == 0:
      texts[1] = "ref: -100..100W {:d}/10s".format(phase_elapsed_seconds)
    elif state == 1:
      texts[1] = "ramp: {:d}/3s".format(phase_elapsed_seconds)
    elif state == 2:
      texts[1] = "load: {:d}/15s".format(phase_elapsed_seconds)
    elif state == 3:
      texts[1] = "collect: {:d}/5".format(sample_count)
    elif state == 4:
      texts[1] = "result available"
    elif state == 5:
      texts[1] = "measurement failed"
    else:
      texts[1] = "measure: unavailable"

    texts[2] = power_text

    if state == 0:
      texts[3] = "samples: {:d}/5".format(reference_sample_count)
    elif state in (1, 2):
      texts[3] = "samples: {:d}/5".format(sample_count)
    elif state == 4:
      texts[3] = "measured: {} moh".format(result)
    elif state == 5:
      texts[3] = "attempts: 25/25"

    texts[4] = "retries: {:d}".format(error_count)
    self._update_lines(texts)
