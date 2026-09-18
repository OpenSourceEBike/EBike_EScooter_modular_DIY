from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font


class BatteryResistanceDebugScreen(BaseScreen):
  """Optional BMS snapshot view for diagnosis outside normal navigation."""

  NAME = "Battery resistance debug"
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

    texts = [""] * 5
    texts[0] = "Battery resistance"
    result = getattr(vars, "battery_resistance_last_mohm", None)
    result = result if result is not None else "na"
    metadata = getattr(vars, "battery_resistance_measurement", {})
    texts[1] = "BMS R: {} moh".format(result)
    texts[2] = "V: {}>{}".format(
      metadata.get("before_voltage_x100", "na"),
      metadata.get("after_voltage_x100", "na"))
    texts[3] = "I: {}>{}".format(
      metadata.get("before_current_x100", "na"),
      metadata.get("after_current_x100", "na"))
    rejection_reason = getattr(vars, "battery_resistance_rejection_reason", "")
    texts[4] = "Reject: " + rejection_reason if rejection_reason else "BASIC x100"
    self._update_lines(texts)
