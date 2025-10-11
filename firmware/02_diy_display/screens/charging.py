
from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import ac437_hp_150_re_12 as font_small

class ChargingScreen(BaseScreen):
    NAME = "Charging"

    def on_enter(self):
        self.clear()
        self.title_bar("Charging")
        self.batt = BatterySOCWidget(self.fb, self.fb.width, self.fb.height)
        self.tbox = WidgetTextBox(self.fb)
        self.tbox.set_box(2, 14, self.fb.width-2, self.fb.height-2)

    def render(self):
        pass