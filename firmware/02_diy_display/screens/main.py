# screens/main.py
import time
import common.config_runtime as cfg
from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_progress_bar import ProgressBarWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import robotobold12 as font_small, robotobold18 as font, robotobold50 as font_big

class MainScreen(BaseScreen):
    NAME = "Main"

    def __init__(self, fb):
        super().__init__(fb)
        self._time_string_previous = ''
        self._motor_power_previous = 0
        self._wheel_speed_x10_previous = 0
        self._one_second = 0
        self._brakes_are_active_previous = ''
        self._lights_state_previous = ''
        self._warning_queue = []
        self._warning_current = None
        self._warning_start_ms = 0
        self._warning_text_previous = ''
        self._warning_showing_progress_bar = False
        self._warning_bar_kind = None
        self._vesc_temp_percent = 0
        self._motor_temp_percent = 0
        self._one_second = time.ticks_add(time.ticks_ms(), 1000)
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
        
        # Warning / progress area
        self._warning_widget = WidgetTextBox(
            self.fb, self.fb.width, self.fb.width,
            font=font_small,
            align_inside="right"
        )
        self._warning_widget.set_box(
            x1=self.fb.width - 40, y1=38,
            x2=self.fb.width - 1, y2=38 + 8
        )
        self._warning_widget.update('')

        # Progress bar
        self._progress_bar_widget = ProgressBarWidget(
            self.fb,
            x=self.fb.width - 40, y=38,
            width=40, height=8,
            label_text="mo",
            label_font=font_small,
            label_gap=2,
            label_dy=-2,
        )
        self._progress_bar_widget.draw_contour()
        self._progress_bar_widget.update(0)
        self._progress_bar_widget.set_visible(False, clear=True)
        
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
        now = time.ticks_ms()
        # Motor power
        if self._motor_power_previous != vars.motor_power_percent:
            self._motor_power_previous = vars.motor_power_percent
            self._motor_power_widget.update(vars.motor_power_percent)

        # Brakes
        if vars.brakes_are_active != self._brakes_are_active_previous:
            self._brakes_are_active_previous = vars.brakes_are_active
            brakes = 'B' if vars.brakes_are_active else ''
            self._brakes_widget.update(brakes)

        # Lights
        if vars.lights_state != self._lights_state_previous:
            self._lights_state_previous = vars.lights_state
            lights = 'L' if vars.lights_state else ''
            self._lights_widget.update(lights)
            
        # Slow tick (about 1 Hz)
        if time.ticks_diff(now, self._one_second) >= 0:
            self._one_second = time.ticks_add(self._one_second, 1000)

            # Battery SOC - only draws if number of bars change
            self._battery_soc_widget.update(vars.battery_soc_x1000 // 10)

            # Wheel speed
            wheel_speed_x10 = vars.wheel_speed_x10
            if wheel_speed_x10 > 999:
                wheel_speed_x10 = 999

            if self._wheel_speed_x10_previous != wheel_speed_x10:
                self._wheel_speed_x10_previous = wheel_speed_x10
                self._wheel_speed_widget.update(wheel_speed_x10 // 10)

            # Time
            if cfg.enable_rtc_time:
                if self._time_string_previous != vars.time_string:
                    self._time_string_previous = vars.time_string
                    self._clock_widget.update(vars.time_string)

        # Progress bar (temperature percent)
        self._update_temp_percents(vars)
        if self._warning_showing_progress_bar:
            percent = self._bar_percent(self._warning_bar_kind)
            if percent <= 0:
                self._warning_current = None
                self._warning_showing_progress_bar = False
                self._warning_bar_kind = None
                self._progress_bar_widget.set_visible(False, clear=True)
            else:
                self._progress_bar_widget.update(percent)

       # Mode (show once for 5s after first entry to main screen, and if mode is diferent from 0)
        if vars.mode != 0 and self._show_mode_once and self._mode_show_started:
            if time.ticks_diff(now, self._mode_show_start_ms) <= 5000:
                mode_text = f"mode {int(vars.mode)}" if vars.mode is not None else ''
                if mode_text != self._warning_text_previous:
                    self._warning_text_previous = mode_text
                    self._progress_bar_widget.set_visible(False, clear=True)
                    self._warning_widget.set_visible(True, clear=True)
                    self._warning_showing_progress_bar = False
                    self._warning_widget.update(mode_text)
            else:
                if self._warning_text_previous != '':
                    self._warning_text_previous = ''
                    self._warning_widget.set_visible(True, clear=True)
                    self._warning_showing_progress_bar = False
                    self._warning_widget.update('')
                self._show_mode_once = False

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
        if not self._queue_has("text", text):
            self._warning_queue.append(("text", text))

    def _enqueue_progress_bar(self, kind):
        self._warning_queue.append(("bar", kind))

    def _enqueue_temp_bars(self):
        if self._vesc_temp_percent > 0:
            self._enqueue_progress_bar_unique("v")
        if self._motor_temp_percent > 0:
            self._enqueue_progress_bar_unique("m")

    def _queue_has(self, kind, payload):
        for item in self._warning_queue:
            if item[0] == kind and item[1] == payload:
                return True
        if self._warning_current is not None:
            return self._warning_current[0] == kind and self._warning_current[1] == payload
        return False

    def _enqueue_progress_bar_unique(self, kind):
        if not self._queue_has("bar", kind):
            self._enqueue_progress_bar(kind)

    def _remove_queue_items(self, kind, payload):
        if not self._warning_queue:
            return
        self._warning_queue = [
            item for item in self._warning_queue
            if not (item[0] == kind and item[1] == payload)
        ]

    def _bar_percent(self, kind):
        if kind == "v":
            return self._vesc_temp_percent
        if kind == "m":
            return self._motor_temp_percent
        return 0

    def _bar_label(self, kind):
        if kind == "v":
            return "ve"
        if kind == "m":
            return "mo"
        return ""

    def _temp_percent(self, temp_x10, min_x10, max_x10):
        if max_x10 <= min_x10:
            return 0
        if temp_x10 <= min_x10:
            return 0
        if temp_x10 >= max_x10:
            return 100
        return int((temp_x10 - min_x10) * 100 / (max_x10 - min_x10))

    def _update_temp_percents(self, vars):
        self._vesc_temp_percent = self._temp_percent(
            vars.vesc_temperature_x10,
            cfg.rear_motor_cfg.vesc_min_temperature_x10,
            cfg.rear_motor_cfg.vesc_max_temperature_x10,
        )
        self._motor_temp_percent = self._temp_percent(
            vars.motor_temperature_x10,
            cfg.rear_motor_cfg.min_temperature_x10,
            cfg.rear_motor_cfg.max_temperature_x10,
        )
        if self._vesc_temp_percent <= 0:
            self._remove_queue_items("bar", "v")
        if self._motor_temp_percent <= 0:
            self._remove_queue_items("bar", "m")
        if self._warning_bar_kind == "v" and self._vesc_temp_percent <= 0:
            self._warning_current = None
            self._warning_showing_progress_bar = False
            self._warning_bar_kind = None
            self._progress_bar_widget.set_visible(False, clear=True)
        if self._warning_bar_kind == "m" and self._motor_temp_percent <= 0:
            self._warning_current = None
            self._warning_showing_progress_bar = False
            self._warning_bar_kind = None
            self._progress_bar_widget.set_visible(False, clear=True)

    def _tick_warning_queue(self):
        now = time.ticks_ms()
        if self._warning_current is None:
            if not self._warning_queue:
                self._enqueue_temp_bars()
            while self._warning_queue:
                kind, payload = self._warning_queue.pop(0)
                if kind == "bar":
                    percent = self._bar_percent(payload)
                    if percent <= 0:
                        continue
                    self._warning_current = ("bar", payload)
                    self._warning_start_ms = now
                    self._warning_showing_progress_bar = True
                    self._warning_bar_kind = payload
                    self._warning_widget.set_visible(False, clear=True)
                    self._progress_bar_widget.set_visible(True, clear=True)
                    self._progress_bar_widget.set_label_text(self._bar_label(payload))
                    self._progress_bar_widget.draw_contour()
                    self._progress_bar_widget.update(percent)
                    break
                else:
                    self._warning_current = ("text", payload)
                    self._warning_start_ms = now
                    if payload != self._warning_text_previous:
                        self._warning_text_previous = payload
                    self._warning_showing_progress_bar = False
                    self._warning_bar_kind = None
                    self._progress_bar_widget.set_visible(False, clear=True)
                    self._warning_widget.set_visible(True, clear=True)
                    self._warning_widget.update(payload)
                    break
        else:
            if time.ticks_diff(now, self._warning_start_ms) > 5000:
                kind, payload = self._warning_current
                if kind == "bar":
                    if self._bar_percent(payload) > 0:
                        if self._warning_queue:
                            self._enqueue_progress_bar(payload)
                        else:
                            # Keep showing if nothing else is queued
                            self._warning_start_ms = now
                            return
                    else:
                        self._progress_bar_widget.set_visible(False, clear=True)
                        self._warning_showing_progress_bar = False
                        self._warning_bar_kind = None
                self._warning_current = None
                if self._warning_text_previous != '':
                    self._warning_text_previous = ''
                    self._warning_widget.update('')
