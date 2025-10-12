import time
from screens.boot import BootScreen
from screens.main import MainScreen
from screens.charging import ChargingScreen
from screens.poweroff import PowerOffScreen
import configurations as cfg

class ScreenManager:
    def __init__(self, fb, vars):
        self.fb = fb
        self.boot    = BootScreen(fb)
        self.main    = MainScreen(fb)
        self.charging     = ChargingScreen(fb)
#         self.power_off    = PowerOffScreen(fb, countdown_s=3, on_poweroff=None)
        self.power_off    = PowerOffScreen(fb)
        self.current = self.boot
        self.current.on_enter()
        self._charge_seen_ms = None
        self._button_power_long_click_previous = 0

    def render(self, vars):
        self.current.render(vars)
        try:
            self.fb.show()
        except Exception:
            pass

    def force(self, name):
        self.current.on_exit()
        if name == "Main":    self.current = self.main
        elif name == "Charging": self.current = self.charging
        elif name == "PowerOff": self.current = self.power_off
        else: self.current = self.boot
        self.current.on_enter()

    def update(self, vars):
        now = time.ticks_ms()
        
        #----- Auto-detect charging (wheel=0 AND ibat>threshold for >= 2s)
        if vars.wheel_speed_x10 == 0 and vars.bms_battery_current_x10 > cfg.charge_current_threshold_a_x10:
            if self._charge_seen_ms is None:
                self._charge_seen_ms = now
            elif time.ticks_diff(now, self._charge_seen_ms) >= cfg.charge_detect_hold_ms:
                if self.current in (self.main,):
                    # enter Charging mode automatically
                    vars.motor_enable_state = False
                    self.force("Charging")
        else:
            self._charge_seen_ms = None

        # ----- Button-based transitions
        button_power_long_click = vars.buttons_state & 0x0200
        if self._button_power_long_click_previous != button_power_long_click:
            self._button_power_long_click_previous = button_power_long_click
        
            # Common preconditions that include wheel speed and sometimes brakes
            if self.current in (self.main,) and vars.wheel_speed_x10 == 0 and vars.brakes_are_active == True:
                # Main -> Charging with brakes
                vars.motor_enable_state = False
                self.force("Charging")
                return

            if self.current in (self.boot,) and vars.wheel_speed_x10 == 0 and vars.brakes_are_active == True:
                # Boot -> Charging with brakes
                vars.motor_enable_state = False
                self.force("Charging")
                return

            if self.current in (self.charging,):
                # Charging -> Main (button long click)
                vars.motor_enable_state = True
                self.force("Main")
                return

            # Power off rule from Main (wheel=0)
            if self.current in (self.main,) and vars.wheel_speed_x10 == 0:
                vars.motor_enable_state = False
                self.force("PowerOff")
                return

            # Boot -> Main (explicit rule)
            if self.current in (self.boot,):
                vars.motor_enable_state = True
                self.force("Main")
                return
