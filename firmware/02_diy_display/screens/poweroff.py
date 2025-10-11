
import time
from .base import BaseScreen

class PowerOffScreen(BaseScreen):
    NAME = "PowerOff"

    def __init__(self, fb, countdown_s=3, on_poweroff=None):
        super().__init__(fb)
        self.countdown_s = countdown_s
        self.on_poweroff = on_poweroff or (lambda: None)
        self._started_at = None

    def on_enter(self):
        self._started_at = time.ticks_ms()
        self.clear()
        self.title_bar("Power Off")
        try:
            self.fb.text("Shutting down...", 4, 16, 1)
        except TypeError:
            self.fb.text(4, 16, "Shutting down...", 1)

    def render(self, data):
        # Show countdown
        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._started_at)
        remain = max(0, self.countdown_s - elapsed_ms // 1000)
        try:
            self.fb.fill_rect(0, 28, self.fb.width, 20, 0)
            self.fb.text("Powering off in: {}s".format(remain), 4, 30, 1)
        except TypeError:
            self.fb.fill_rect(0, 28, self.fb.width, 20, 0)
            self.fb.text(4, 30, "Powering off in: {}s".format(remain), 1)

        if remain <= 0:
            self.on_poweroff()
