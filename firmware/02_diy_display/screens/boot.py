import time
from .base import BaseScreen
from widgets.widget_text_box import WidgetTextBox
from widgets.widget_battery_soc import BatterySOCWidget
from fonts import freesansbold16 as font1
from fonts import freesansbold12 as font2

class BootScreen(BaseScreen):
    NAME = "Boot"

    def __init__(self, fb):
        super().__init__(fb)
        self._battery_soc_updated = False

    def on_enter(self):
        self.clear()
        
        # Title
        self._title = WidgetTextBox(
            self.fb, self.fb.width, self.fb.height,
            font=font1,
            align_inside="center"
        )
        self._title.set_box(x1=0, y1=20, x2=self.fb.width - 1, y2=40)
         
        # Battery SOC widget
        batt_scale = 2
        batt_x = 18
        batt_y = 18
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.set_blink_timing(600, 300)
        self._battery_soc_widget.set_charging(False)
        self._battery_soc_widget.update(0)
        self._battery_soc_widget.hide()

        # Battery SOC
        self._battery_soc = WidgetTextBox(
            self.fb, self.fb.width, self.fb.height,
            font=font2,
            align_inside="center"
        )
        self._battery_soc.set_box(x1=20, y1=self.fb.height - 12, x2=22+46+40, y2=self.fb.height - 1)
        self._battery_soc.update('')
        self._battery_soc.hide()

    def render(self, vars):

        # If negative, means it was not updated yet
        if not self._battery_soc_updated and vars.battery_soc_x1000 >= 0:
            self._battery_soc_updated = True
    
            # Enable the widgets and move title to top
            self._battery_soc_widget.show()
            self._battery_soc.show()
            self._title.set_box(x1=0, y1=0, x2=self.fb.width - 1, y2=16)
            self._title.update('Ready')
           
        else:
            self._title.update('Ready')
            
            
        self._battery_soc_widget.update(vars.battery_soc_x1000//10)
        self._battery_soc.update(f"{vars.battery_soc_x1000 / 10:.0f} %")


