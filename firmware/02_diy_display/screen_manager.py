import time
from screens.boot import BootScreen
from screens.main import MainScreen
from screens.charging import ChargingScreen
from screens.poweroff import PowerOffScreen

class ScreenManager:
    def __init__(self, fb, vars):
        self.fb = fb
        self.boot    = BootScreen(fb)
        self.main    = MainScreen(fb)
        self.chg     = ChargingScreen(fb)
#         self.poff    = PowerOffScreen(fb, countdown_s=3, on_poweroff=None)
        self.poff    = PowerOffScreen(fb)
        self.current = self.boot
        self.current.on_enter()
        self._charge_seen_ms = None

    def render(self):
        self.current.render()
        try:
            self.fb.show()
        except Exception:
            pass

    def force(self, name):
        self.current.on_exit()
        if name == "Main":    self.current = self.main
        elif name == "Charging": self.current = self.chg
        elif name == "PowerOff": self.current = self.poff
        else: self.current = self.boot
        self.current.on_enter()

    def update(self, *, long_click=False, wheel_kmh=0.0, brakes=False, ibat_a=0.0):
        now = time.ticks_ms()

        # ----- Auto-detect charging (wheel=0 AND ibat>threshold for >= 2s)
        # if wheel_kmh <= WHEEL_STOP_KMH and ibat_a > CHARGE_CURRENT_THRESHOLD_A:
        #     if self._charge_seen_ms is None:
        #         self._charge_seen_ms = now
        #     elif time.ticks_diff(now, self._charge_seen_ms) >= CHARGE_DETECT_HOLD_MS:
        #         if self.current in (self.main,):
        #             # enter Charging automatically
        #             set_motor_enabled(False)
        #             self.force("Charging")
        # else:
        #     self._charge_seen_ms = None

        # ----- Button-based transitions
        # if long_click:
        #     # Common preconditions that include wheel speed and sometimes brakes
        #     if self.current in (self.main,) and wheel_kmh <= WHEEL_STOP_KMH and brakes:
        #         # Main -> Charging with brakes
        #         set_motor_enabled(False)
        #         self.force("Charging")
        #         return

        #     if self.current in (self.boot,) and wheel_kmh <= WHEEL_STOP_KMH and brakes:
        #         # Boot -> Charging with brakes
        #         set_motor_enabled(False)
        #         self.force("Charging")
        #         return

        #     if self.current in (self.chg,):
        #         # Charging -> Main (button long click)
        #         set_motor_enabled(True)
        #         self.force("Main")
        #         return

        #     # Power off rule from Boot or Main (wheel=0)
        #     if self.current in (self.main, self.boot) and wheel_kmh <= WHEEL_STOP_KMH:
        #         set_motor_enabled(False)
        #         self.force("PowerOff")
        #         return

        #     # Boot -> Main (explicit rule)
        #     if self.current in (self.boot,):
        #         set_motor_enabled(True)
        #         self.force("Main")
        #         return
