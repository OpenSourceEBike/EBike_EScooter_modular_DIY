# screens/screen_manager.py
from screens.boot import BootScreen
from screens.main import MainScreen
from screens.charging import ChargingScreen
from screens.poweroff import PowerOffScreen

# Lightweight "enum" that works on MicroPython
class ScreenID:
    BOOT      = 0
    MAIN      = 1
    CHARGING  = 2
    POWEROFF  = 3

class ScreenManager:
    def __init__(self, fb, vars):
        self.fb = fb

        # Create instances once
        self._boot      = BootScreen(fb)
        self._main      = MainScreen(fb)
        self._charging  = ChargingScreen(fb)
        self._poweroff  = PowerOffScreen(fb)

        # Map IDs <-> instances
        self._screens = {
            ScreenID.BOOT:     self._boot,
            ScreenID.MAIN:     self._main,
            ScreenID.CHARGING: self._charging,
            ScreenID.POWEROFF: self._poweroff,
        }

        # Start in BOOT
        self._current_id = ScreenID.BOOT
        self._current = self._screens[self._current_id]
        self._current.on_enter()

        self._button_power_long_click_previous = False
        self._button_power_click_previous = False
        self._charging_state_previous = False
        self._screen_previous = ScreenID.BOOT

    # ---- Convenience getters ----
    def get_current_id(self):
        """Return the numeric ScreenID (fast, no strings)."""
        return self._current_id

    def get_current(self):
        """Return the current screen instance if you need to call methods."""
        return self._current

    def current_is(self, screen_id):
        """Fast equality without tuples/strings."""
        return self._current_id == screen_id

    # ---- Core operations ----
    def render(self, vars):
        self._current.render(vars)
        try:
            self.fb.show()
        except Exception:
            pass

    def force(self, screen_id):
        """Switch to a screen by numeric ID (no strings!)."""
        if screen_id == self._current_id:
            return
        self._current.on_exit()
        self._current_id = screen_id
        self._current = self._screens[screen_id]
        self._current.on_enter()

    def update(self, vars):
        
        button_power_click = bool(vars.buttons_state & 0x0100)
        button_power_long_click = bool(vars.buttons_state & 0x0200)
        is_charging = vars.battery_is_charging

        # If Charging state changed
        if is_charging != self._charging_state_previous:
            self._charging_state_previous = is_charging
            
            # If is now Charging and not in Charging screen, go to Charging screen
            if is_charging and \
                not self.current_is(ScreenID.CHARGING):
                vars.motor_enable_state = False
                self._screen_previous = self.get_current_id()
                self.force(ScreenID.CHARGING)
                return
            
            # If is now not Charging and in Charging screen, go to Charging screen
            if not is_charging and \
                self.current_is(ScreenID.CHARGING):
                
                screen_previous = self._screen_previous
                self._screen_previous = self.get_current_id()
                
                # Needs to go to Main, so enable the motor
                if screen_previous == ScreenID.MAIN:
                    vars.motor_enable_state = True
                # Not Main screen, so disable the motor
                else:
                    vars.motor_enable_state = False
                    
                self.force(screen_previous)
                return
            
        # Short click: Boot -> Main
        if self._button_power_click_previous != button_power_click:
            self._button_power_click_previous = button_power_click

            # We are in Boot scren, so go to Main screen
            if self.current_is(ScreenID.BOOT):
                vars.motor_enable_state = True
                self._screen_previous = self.get_current_id()
                self.force(ScreenID.MAIN)
                return
                
            # We are in Power off screen, so restart the display
            elif self.current_is(ScreenID.POWEROFF):
                import machine
                machine.reset()
                return
            
        wheel_stopped = (vars.wheel_speed_x10 == 0)
        brakes_on = bool(vars.brakes_are_active)

        # Long click transitions
        if self._button_power_long_click_previous != button_power_long_click:
            self._button_power_long_click_previous = button_power_long_click

            # Go to Charging
            if (self.current_is(ScreenID.BOOT) or \
                self.current_is(ScreenID.MAIN)) and \
                wheel_stopped and \
                brakes_on:
                vars.motor_enable_state = False
                self._screen_previous = self.get_current_id()
                self.force(ScreenID.CHARGING)
                return

            # Go to Main
            if self.current_is(ScreenID.CHARGING):
                vars.motor_enable_state = True
                self._screen_previous = self.get_current_id()
                self.force(ScreenID.MAIN)
                return

            # Go to Power off
            if self.current_is(ScreenID.MAIN) and wheel_stopped:
                vars.motor_enable_state = False
                vars.shutdown_request = True
                self._screen_previous = self.get_current_id()
                self.force(ScreenID.POWEROFF)
                return
