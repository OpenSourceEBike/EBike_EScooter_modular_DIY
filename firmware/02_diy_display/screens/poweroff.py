from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import freesansbold16 as font

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
        self._title.set_box(x1=0, y1=20, x2=self.fb.width - 1, y2=40)
        self._title.update('Powering off')

    def render(self, vars):
        pass
