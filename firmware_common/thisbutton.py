import time
from machine import Pin

def _ticks_ns():
    # MicroPython has ticks_ns() on most modern ports; fall back if needed.
    try:
        return time.ticks_ns()
    except AttributeError:
        return time.ticks_us() * 1000

class thisButton:
    def __init__(self, gpio, pull_up=True):
        # gpio can be an int (pin number) or a Pin object
        self.pin = gpio if isinstance(gpio, Pin) else Pin(gpio, Pin.IN)
        # configure pull
        try:
            self.pin.init(Pin.IN, Pin.PULL_UP if pull_up else Pin.PULL_DOWN)
        except (AttributeError, ValueError):
            # Some MCUs might lack PULL_DOWN; if so, leave floating and expect external pull
            self.pin.init(Pin.IN)

        self.prev_state = None
        self.cur_state = None
        # active state = low when pull_up (pressed ties to GND), else high
        self.activated_state = 0 if pull_up else 1

        self.cur_time = None
        self.prev_state_change = None
        self.active = False
        self.long_press_activated = False
        self.debounce_start = 0
        self.debouncing = False
        self.held = False

        self.click_start_function = None
        self.click_release_function = None
        self.long_press_start_function = None
        self.long_press_release_function = None
        self.held_function = None
        self.click_only_assigned = False

        # defaults in nanoseconds (match your CP values):
        # 5 ms, 500 ms, 100 ms
        self.default_debounce_threshold = 5_000_000
        self.default_long_press_threshold = 500_000_000
        self.default_held_interval = 100_000_000

        self.debounce_threshold = self.default_debounce_threshold
        self.long_press_threshold = self.default_long_press_threshold
        self.held_interval = self.default_held_interval
        self.held_next_time = 0

        self.debug = False

    # this needs to be called frequently from the main loop
    def tick(self):
        self.cur_time = _ticks_ns()

        # read the pin and start debounce when a change is detected
        if not self.debouncing:
            self.cur_state = 1 if self.pin.value() else 0
            if self.cur_state != self.prev_state:
                self.start_debounce()

        # finish debounce delay
        if self.debouncing and self.cur_time > (self.debounce_start + self.debounce_threshold):
            self.debouncing = False

        if self.cur_state == self.activated_state:
            # button is active this cycle
            if self.active is not True:
                # just pressed
                self.active = True
                self.prev_state_change = self.cur_time
                if self.debug:
                    print("Click Down")
                # if only click is defined, fire now
                if self.click_start_function is not None and self.click_only_assigned:
                    try:
                        self.click_start_function()
                    except Exception as e:
                        if self.debug: print("click_start error:", e)
            else:
                # still held
                if (self.cur_time - self.prev_state_change) > self.long_press_threshold:
                    # Long-press start
                    if (self.long_press_activated is not True) and (self.long_press_start_function is not None):
                        if self.debug:
                            print("Long press start Detected")
                        self.long_press_activated = True
                        self.active = False  # block further detections until release
                        try:
                            self.long_press_start_function()
                        except Exception as e:
                            if self.debug: print("long_press_start error:", e)
                    # Held repeat
                    elif self.held_function is not None:
                        self.long_press_activated = True
                        if not self.held:
                            self.held = True
                            try:
                                self.held_function()
                            except Exception as e:
                                if self.debug: print("held first error:", e)
                            self.held_next_time = self.cur_time + self.held_interval
                        elif self.cur_time > self.held_next_time:
                            try:
                                self.held_function()
                            except Exception as e:
                                if self.debug: print("held repeat error:", e)
                            self.held_next_time = self.cur_time + self.held_interval

        # button released (and not bouncing)
        elif (self.cur_state != self.activated_state) and (self.active is True):
            if self.long_press_activated:
                # long press / held release
                self.long_press_activated = False
                self.active = False
                self.held = False
                if self.long_press_release_function is not None:
                    try:
                        self.long_press_release_function()
                    except Exception as e:
                        if self.debug: print("long_press_release error:", e)
                if self.debug:
                    print("Long press or hold duration:", self.cur_time - self.prev_state_change)
            else:
                # click release
                self.active = False
                if (self.click_start_function is not None) and (not self.click_only_assigned):
                    try:
                        self.click_start_function()
                    except Exception as e:
                        if self.debug: print("click_start (release path) error:", e)
                if self.click_release_function is not None:
                    try:
                        self.click_release_function()
                    except Exception as e:
                        if self.debug: print("click_release error:", e)
                if self.debug:
                    print("Click release, duration:", self.cur_time - self.prev_state_change)

        self.prev_state = self.cur_state

    # ----- utils -----
    def msToNs(self, milliseconds):
        return int(milliseconds) * 1_000_000

    def nsToMs(self, nanoseconds):
        return nanoseconds / 1_000_000.0

    def start_debounce(self):
        self.debouncing = True
        self.debounce_start = self.cur_time

    # ----- callback registration -----
    def assignClickStart(self, function_name):
        self.click_start_function = function_name
        if (self.long_press_start_function is None and
            self.long_press_release_function is None and
            self.held_function is None):
            self.click_only_assigned = True

    def assignClickRelease(self, function_name):
        self.click_release_function = function_name

    def assignLongClickStart(self, function_name):
        self.long_press_start_function = function_name
        self.click_only_assigned = False

    def assignLongClickRelease(self, function_name):
        self.long_press_release_function = function_name
        self.click_only_assigned = False

    def assignHeld(self, function_name, milliseconds=-1):
        self.held_function = function_name
        self.click_only_assigned = False
        if milliseconds < 0:
            self.held_interval = self.default_held_interval
        else:
            self.held_interval = self.msToNs(milliseconds)

    # ----- configuration -----
    def toggleDebug(self):
        self.debug = not self.debug

    def setDebounceThreshold(self, milliseconds=-1):
        self.debounce_threshold = (
            self.default_debounce_threshold if milliseconds < 0 else self.msToNs(milliseconds)
        )

    def setLongPressThreshold(self, milliseconds=-1):
        self.long_press_threshold = (
            self.default_long_press_threshold if milliseconds < 0 else self.msToNs(milliseconds)
        )

    def setHeldInterval(self, milliseconds=-1):
        self.held_interval = (
            self.default_held_interval if milliseconds < 0 else self.msToNs(milliseconds)
        )

    # ----- properties -----
    @property
    def isHeld(self):
        # True if a long press or hold is active
        return self.long_press_activated

    @property
    def heldDuration(self):
        # ms held (0 if not in long-press/hold)
        if self.long_press_activated:
            return self.nsToMs(_ticks_ns() - self.prev_state_change)
        return 0

    @property
    def gpio_state(self):
        # deprecated alias (kept for compatibility)
        return 1 if self.pin.value() else 0

    @property
    def gpioState(self):
        return 1 if self.pin.value() else 0

    @property
    def buttonActive(self):
        # True while button is currently pressed after debouncing (not during suppressed long-press)
        return bool(self.active)

