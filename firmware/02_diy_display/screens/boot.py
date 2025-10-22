import time
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from widgets.widget_battery_soc import BatterySOCWidget
from fonts import freesansbold14

class BootScreen(BaseScreen):
    NAME = "Boot"

    def __init__(self, fb):
        super().__init__(fb)
        self._time_timer_previous = 0

    def on_enter(self):
        self.clear()
        
        # Title
        self._title = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=freesansbold14,
            align_inside="center"
        )
        self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=20)
        self._title.update('Ready')
        
        # Battery SOC widget
        batt_scale = 2
        batt_x = 18
        batt_y = 18
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.set_blink_timing(600, 300)
        self._battery_soc_widget.set_charging(False)
        self._battery_soc_widget.update(0)
        

        # Battery SOC	
        self._battery_soc = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=freesansbold14,
            align_inside="center"
        )
        self._battery_soc.set_box(x1=20, y1=self.fb.height - 12, x2=22+46+40, y2=self.fb.height - 1)
        self._battery_soc.update('')

    def render(self, vars):
        self._battery_soc_widget.update(vars.battery_soc_x1000//10)

        self._battery_soc.update(f"{vars.battery_soc_x1000 / 10:.0f} %")


