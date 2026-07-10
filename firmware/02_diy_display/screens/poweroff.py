from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small, robotobold18 as font

class PowerOffScreen(BaseScreen):
  NAME = "PowerOff"

  def on_enter(self):
    self.clear()
    
    # Title
    self._title = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font,
      align_inside="center"
    )
    self._title.set_box(x1=0, y1=23, x2=self.fb.width - 1, y2=40)
    self._title.update('Powering off')
    self._warning_widget = WidgetTextBox(
      self.fb, self.fb.width, self.fb.width,
      font=font_small,
      align_inside="right"
    )
    self._warning_widget.set_box(
      x1=self.fb.width - 40, y1=38,
      x2=self.fb.width - 1, y2=38 + 8
    )
    self._warning_widget.update('')

  def render(self, vars):
    comms_paused = bool(getattr(vars, "comms_paused", False))
    warning = 'p TX!' if not comms_paused and not vars.power_switch_board_comm_ok else ''
    self._warning_widget.update(warning)
