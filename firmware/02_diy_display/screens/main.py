from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font


class MainScreen(BaseScreen):
  """Temporary riding view for battery-resistance diagnostics."""

  NAME = "Main"
  _STATE_NAMES = {
    -1: "unavailable",
    0: "reference qual",
    1: "waiting load",
    2: "load qualify",
    3: "complete",
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
    state = int(getattr(vars, "battery_resistance_debug_phase", -1))
    texts = [""] * 5
    texts[0] = "{}: {}".format(
      state, self._STATE_NAMES.get(state, "unknown"))
    boot_seconds = int(getattr(
      vars, "battery_resistance_debug_boot_seconds", 0))
    error_count = int(getattr(
      vars, "battery_resistance_debug_error_count", 0))
    sample_count = int(getattr(
      vars, "battery_resistance_debug_sample_count", 0))
    reference_sample_count = int(getattr(
      vars, "battery_resistance_debug_reference_sample_count", 0))
    result = getattr(vars, "battery_resistance_last_mohm", None)
    result = result if result is not None else "na"
    motor_rx = "ok" if getattr(vars, "motor_board_rx_ok", False) else "FAIL"

    if state == 0:
      texts[1] = "boot: {:d}/60".format(boot_seconds)
    elif state == 1:
      texts[1] = "reference: ok"
    elif state == 2:
      texts[1] = "load: qualifying"
    elif state == 3:
      texts[1] = "result available"
    else:
      texts[1] = "measure: unavailable"

    if state == 0:
      texts[2] = "200W secs total"
    elif state != 3:
      texts[2] = "retries: {:d}".format(error_count)

    if state == 0:
      texts[3] = "last ref: {:d}/3".format(reference_sample_count)
    elif state == 2:
      texts[3] = "last samples: {:d}/3".format(sample_count)
    elif state == 3:
      texts[3] = "measured: {} mOhm".format(result)

    texts[4] = "motor rx: {}".format(motor_rx)
    self._update_lines(texts)
