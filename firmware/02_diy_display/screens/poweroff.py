from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import freesans20 as font

class PowerOffScreen(BaseScreen):
    NAME = "PowerOff"

    # def __init__(self, fb, countdown_s=3, on_poweroff=None):
    #     super().__init__(fb)
    #     self.countdown_s = countdown_s
    #     self.on_poweroff = on_poweroff or (lambda: None)
    #     self._started_at = None

    def on_enter(self):
        self.clear()
        
        box_1 = WidgetTextBox(self.fb, self.fb.width-1, self.fb.width-1,
                                        font=font,
                                        align_inside="center")
        box_1.set_box(x1=0, y1=int(self.fb.height/4)*1, x2=self.fb.width-1, y2=int(self.fb.height/4)*2)

        box_2 = WidgetTextBox(self.fb, self.fb.width-1, self.fb.height,
                                                font=font,
                                                align_inside="center")
        box_2.set_box(x1=0, y1=int(self.fb.height/4)*3, x2=self.fb.width-1, y2=int(self.fb.height/4)*4)
        
        box_1.update("Ready to")
        box_2.update("POWER OFF")

    def render(self, vars):
        pass
