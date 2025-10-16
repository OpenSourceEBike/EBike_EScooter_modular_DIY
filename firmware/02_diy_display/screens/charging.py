
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from widgets.widget_battery_soc import BatterySOCWidget
from fonts import freesans20 as font

class ChargingScreen(BaseScreen):
    NAME = "Charging"

    def on_enter(self):
        self.clear()
        
        # BATTERY SOC
        batt_scale = 2
        # Place at bottom-left, keeping 1px margin
        batt_x = 18
        batt_y = 0
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.set_blink_timing(600, 300)
        self._battery_soc_widget.set_charging(True)
        self._battery_soc_widget.update(0)

    def render(self, vars):
        #self._battery_soc_widget.update(vars.battery_soc_x1000//10)
        self._battery_soc_widget.update(85)