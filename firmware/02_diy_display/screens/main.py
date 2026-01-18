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
        self._brakes_text_previous = ''
        self._lights_text_previous = ''
        self._warning_queue = []
        self._warning_current = None
        self._warning_start_ms = 0
        self._warning_text_previous = ''
        self._mode_last_seen = None
        self._mode_enqueued_once = False
        self._show_mode_once = False
        self._mode_show_started = False
        self._mode_show_start_ms = 0

    def on_enter(self):
        self.clear()
        self._warning_queue = []
        self._warning_current = None
        self._warning_start_ms = 0
        self._warning_text_previous = ''

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

        # Lights
        self._lights_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="left"
        )
        self._lights_widget.set_box(x1=1, y1=37, x2=7, y2=37 + 9)
        self._lights_widget.update('')

        # Brakes
        self._brakes_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="left"
        )
        self._brakes_widget.set_box(x1=12, y1=37, x2=19, y2=37 + 9)
        self._brakes_widget.update('')
        
        # Warning
        self._warning_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="right"
        )
        self._warning_widget.set_box(x1=64, y1=37, x2=127, y2=37 + 9)
        self._warning_widget.update('')
        if not self._mode_enqueued_once:
            self._enqueue_warning(self._mode_text_from_vars())
            self._mode_enqueued_once = True
            self._show_mode_once = True
            self._mode_show_started = True
            self._mode_show_start_ms = time.ticks_ms()
        else:
            self._show_mode_once = False
            self._mode_show_started = False
        self._mode_last_seen = None

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

        # Brakes
        brakes = 'B' if vars.brakes_are_active else ''
        if brakes != self._brakes_text_previous:
            self._brakes_text_previous = brakes
            self._brakes_widget.update(brakes)

        # Lights
        lights = 'L' if vars.lights_state else ''
        if lights != self._lights_text_previous:
            self._lights_text_previous = lights
            self._lights_widget.update(lights)

        # Mode (show once for 5s after first entry to main screen, and if mode is diferent from 0)
        if vars.mode != 0 and self._show_mode_once and self._mode_show_started:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._mode_show_start_ms) <= 5000:
                mode_text = f"mode {int(vars.mode)}" if vars.mode is not None else ''
                if mode_text != self._warning_text_previous:
                    self._warning_text_previous = mode_text
                    self._warning_widget.update(mode_text)
            else:
                if self._warning_text_previous != '':
                    self._warning_text_previous = ''
                    self._warning_widget.update('')
                self._show_mode_once = False
            
        # Time
        if cfg.enable_rtc_time:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._time_timer_previous) > 1000:
                self._time_timer_previous = now
                self._clock_widget.update(vars.time_string)

        # Track mode value (enqueue on change)
        if self._mode_last_seen is None:
            self._mode_last_seen = vars.mode
        elif vars.mode != self._mode_last_seen:
            self._mode_last_seen = vars.mode
            self._enqueue_warning(self._mode_text_from_vars())

        # Warning queue display (5s each)
        self._tick_warning_queue()

    def _mode_text_from_vars(self):
        if self._mode_last_seen is None:
            return ''
        return f"mode {int(self._mode_last_seen)}"

    def _enqueue_warning(self, text):
        if text is None or text == '':
            return
        self._warning_queue.append(text)

    def _tick_warning_queue(self):
        now = time.ticks_ms()
        if self._warning_current is None:
            if self._warning_queue:
                self._warning_current = self._warning_queue.pop(0)
                self._warning_start_ms = now
                if self._warning_current != self._warning_text_previous:
                    self._warning_text_previous = self._warning_current
                    self._warning_widget.update(self._warning_current)
        else:
            if time.ticks_diff(now, self._warning_start_ms) > 5000:
                self._warning_current = None
                if self._warning_text_previous != '':
                    self._warning_text_previous = ''
                    self._warning_widget.update('')
