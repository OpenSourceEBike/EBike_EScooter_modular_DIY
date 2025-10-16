from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import ac437_hp_150_re_12 as font_small, freesans20 as font, freesansbold50 as font_big

class MainScreen(BaseScreen):
    NAME = "Main"

    def on_enter(self):
        self.clear()

        # Motor power widget
        self._motor_power_widget = MotorPowerWidget(self.fb, self.fb.width, self.fb.width)
        self._motor_power_widget.update(0)

        # BATTERY SOC
        batt_scale = 1
        # Place at bottom-left, keeping 1px margin
        batt_x = 1
        batt_y = self.fb.height - (15 * batt_scale) - 1  # 15px is the unscaled total height
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.update(0)

        # Wheel speed on the right
        self._wheel_speed_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_big,
            left=0, top=2, right=1, bottom=0,
            align_inside="right",
            debug_box=False
        )
        self._wheel_speed_widget.set_box(x1=self.fb.width - 55, y1=0, x2=self.fb.width - 1, y2=36)
        self._wheel_speed_widget.update(0)

        # Warning
        self._warning_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="left"
        )
        self._warning_widget.set_box(x1=0, y1=38, x2=63, y2=38 + 9)
        self._warning_widget.update('')

        # Clock
        self._clock_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font,
            align_inside="right"
        )
        self._clock_widget.set_box(x1=self.fb.width - 52, y1=self.fb.width - 17, x2=self.fb.width - 3, y2=self.fb.width - 2)
        self._clock_widget.update('')

    def render(self, vars):
        
        self._motor_power_widget.update(vars.motor_power)
        
        self._battery_soc_widget.update(vars.battery_soc_x1000 // 10)
        
        self._wheel_speed_widget.update(vars.wheel_speed_x10 // 10)
        
        # TODO
        self._warning_widget.update('brakes*')
        
        # TODO
        self._clock_widget.update('9:10')