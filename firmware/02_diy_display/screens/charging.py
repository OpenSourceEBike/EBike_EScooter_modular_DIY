from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from widgets.widget_battery_soc import BatterySOCWidget
from fonts import robotobold18 as font1
from fonts import robotobold14 as font2

class ChargingScreen(BaseScreen):
    NAME = "Charging"

    def __init__(self, fb):
        super().__init__(fb)

    def on_enter(self):
        self.clear()
        
        # Title
        self._title = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font1,
            align_inside="center"
        )
        self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=20)
        self._title.update('Charging')
        
        # Battery SOC widget
        batt_scale = 2
        batt_x = 18
        batt_y = 21
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.set_blink_timing(600, 300)
        self._battery_soc_widget.set_charging(True)
        self._battery_soc_widget.update(0)
        
        # Battery voltage
        self._battery_voltage = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font2,
            align_inside="left"
        )
        self._battery_voltage.set_box(x1=26, y1=self.fb.height - 12, x2=26+37, y2=self.fb.height - 1)
        self._battery_voltage.update('')

        # Battery SOC	
        self._battery_soc = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font2,
            align_inside="right"
        )
        self._battery_soc.set_box(x1=26+43, y1=self.fb.height - 12, x2=26+42+32, y2=self.fb.height - 1)
        self._battery_soc.update('')


    def render(self, vars):

        battery_soc_x1000 = max(vars.battery_soc_x1000, 0)
        self._battery_soc_widget.update(battery_soc_x1000//10)
        self._battery_soc.update(f"{battery_soc_x1000 / 10:.0f} %")
        self._battery_voltage.update(f"{vars.battery_voltage_x10 / 10:.1f} v")
