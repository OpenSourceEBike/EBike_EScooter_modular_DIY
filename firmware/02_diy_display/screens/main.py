# screens/main.py
import time
import configurations as cfg
from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small, robotobold18 as font, robotobold50 as font_big

class MainScreen(BaseScreen):
    NAME = "Main"

    def __init__(self, fb):
        super().__init__(fb)
        self._motor_power_previous = 0
        self._wheel_speed_x10_previous = 0
        self._time_timer_previous = 0
        self._warning_text_previous = ''

    def on_enter(self):
        self.clear()

        # Motor power widget
        self._motor_power_widget = MotorPowerWidget(self.fb, self.fb.width, self.fb.width)
        self._motor_power_widget.update(0)

        # Battery SOC
        batt_scale = 1
        # Place at bottom-left, keeping 1px margin
        batt_x = 1
        batt_y = self.fb.height - (15 * batt_scale) - 1  # 15px is the unscaled total height
        self._battery_soc_widget = BatterySOCWidget(self.fb, x=batt_x, y=batt_y, scale=batt_scale)
        self._battery_soc_widget.draw_contour()
        self._battery_soc_widget.update(0)

        # Wheel speed
        self._wheel_speed_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_big,
            left=0, top=5, right=1, bottom=0,
            align_inside="right"
        )
        self._wheel_speed_widget.set_box(x1=self.fb.width - 55, y1=0, x2=self.fb.width - 1, y2=36)
        self._wheel_speed_widget.update(0)

        # Warning
        self._warning_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="left"
        )
        self._warning_widget.set_box(x1=0, y1=37, x2=63, y2=37 + 9)
        self._warning_widget.update('')

        # Clock
        if cfg.enable_rtc_time:
            self._clock_widget = WidgetTextBox(
                self.fb, self.fb.width, self.fb.width,
                font=font,
                align_inside="right",
            )
            self._clock_widget.set_box(x1=self.fb.width - 49, y1=self.fb.height - 17, x2=self.fb.width - 6, y2=self.fb.height - 2)
            self._clock_widget.update('')

    def render(self, vars):
        # Motor power
        if self._motor_power_previous != vars.motor_power:
            self._motor_power_previous = vars.motor_power
            self._motor_power_widget.update(vars.motor_power)

        # Battery SOC - only draws if number of bars change
        self._battery_soc_widget.update(vars.battery_soc_x1000 // 10)

        # Wheel speed
        wheel_speed_x10 = max(vars.wheel_speed_x10, 0)
        if self._wheel_speed_x10_previous != wheel_speed_x10:
            self._wheel_speed_x10_previous = wheel_speed_x10
            self._wheel_speed_widget.update(wheel_speed_x10 // 10)

        # Lights and brakes
        if vars.brakes_are_active and vars.lights_state:
            warning_text = 'B L'
            
        elif vars.brakes_are_active:
            warning_text = 'B'

        elif vars.lights_state:
            warning_text = '  L'

        else:
            # Neither active: ''
            warning_text = ''
            
        if warning_text != self._warning_text_previous:
            self._warning_text_previous = warning_text
            self._warning_widget.update(warning_text)

        # Time
        if cfg.enable_rtc_time:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._time_timer_previous) > 1000:
                self._time_timer_previous = now
                self._clock_widget.update(vars.time_string)

