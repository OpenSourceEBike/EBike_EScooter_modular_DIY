
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

    def render(self):
        pass
