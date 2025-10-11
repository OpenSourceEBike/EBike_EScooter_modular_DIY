
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from fonts import freesans20 as font

class ChargingScreen(BaseScreen):
    NAME = "Charging"

    def on_enter(self):
        self.clear()
        
        box_1 = WidgetTextBox(self.fb, self.fb.width-1, self.fb.width-1,
                                        font=font,
                                        align_inside="center")
        box_1.set_box(x1=0, y1=int(self.fb.height/4)*1, x2=self.fb.width-1, y2=int(self.fb.height/4)*3)
        
        box_1.update("Charging...")

    def render(self):
        pass