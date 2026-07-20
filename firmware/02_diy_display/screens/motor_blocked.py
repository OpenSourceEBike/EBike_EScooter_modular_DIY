from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold18 as font


class MotorBlockedScreen(BaseScreen):
  NAME = "Motor blocked"

  def __init__(self, fb):
    super().__init__(fb)
    self._title = WidgetTextBox(
      self.fb, self.fb.width, self.fb.height,
      font=font,
      align_inside="center",
    )
    self._instruction = WidgetTextBox(
      self.fb, self.fb.width, self.fb.height,
      font=font,
      align_inside="center",
    )

    # Centre two text lines with one full line of vertical space between them.
    line_height = font.height()
    block_height = line_height * 3
    top = max(0, (self.fb.height - block_height) // 2)
    self._title.set_box(
      x1=0, y1=top,
      x2=self.fb.width - 1, y2=top + line_height - 1,
    )
    self._instruction.set_box(
      x1=0, y1=top + (line_height * 2),
      x2=self.fb.width - 1,
      y2=top + (line_height * 3) - 1,
    )

  def on_enter(self):
    self.clear()
    self._title.update("motor blocked")
    self._instruction.update("release throttle")

  def render(self, vars):
    pass
