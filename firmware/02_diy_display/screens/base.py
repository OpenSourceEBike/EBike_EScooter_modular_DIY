
# screens/base.py — common helpers

class BaseScreen:
    NAME = "Base"

    def __init__(self, fb):
        self.fb = fb  # framebuf-like object with fill, fill_rect, rect, text, show()

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def clear(self):
        self.fb.fill(0)
