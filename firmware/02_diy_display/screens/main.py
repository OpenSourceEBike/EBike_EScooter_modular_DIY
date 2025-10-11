
from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import freesans20 as font, freesansbold50 as font_big

class MainScreen(BaseScreen):
    NAME = "Main"

    def on_enter(self):
        self.clear()
        self.title_bar("Main")
        # Widgets
        self.batt = BatterySOCWidget(self.fb, self.fb.width, self.fb.height)
        self.power = MotorPowerWidget(self.fb, self.fb.width, self.fb.height)
        self.text = WidgetTextBox(self.fb)
        self.text.set_box(70, 14, self.fb.width-2, 40)

    def render(self, data):
        self.fb.fill_rect(0, 12, self.fb.width, self.fb.height-12, 0)
        # Battery SOC on lower-left
        soc = int(data.get("soc", 0))
        self.batt.draw(soc)
        # Motor power progress (0..100)
        mp = max(0, min(int(data.get("motor_pct", 0)), 100))
        self.power.update(mp)
        # Speed text
        self.text.set_text("{:.1f} km/h".format(data.get("speed", 0.0)), align_inside="left")
        self.text.update()
