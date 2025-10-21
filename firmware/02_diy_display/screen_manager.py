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
        self.power_off    = PowerOffScreen(fb)
        self.current = self.charging
        self.current.on_enter()
        self._charge_seen_ms = None
        self._button_power_long_click_previous = 0
        self._charging_state_previous = False

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
        
        # Enter charging screen
        if vars.battery_is_charging != self._charging_state_previous:
            self._charging_state_previous = vars.battery_is_charging
            vars.motor_enable_state = False
            self.force("Charging")

        # Button-based transitions
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
                vars.shutdown_request = True
                self.force("PowerOff")
                return

            # Boot -> Main (explicit rule)
            if self.current in (self.boot,):
                vars.motor_enable_state = True
                self.force("Main")
                return
