
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
        try:
            self.fb.fill(0)
        except AttributeError:
            # Fallback if no fill(), try a full-rect
            self.fb.fill_rect(0, 0, self.fb.width, self.fb.height, 0)

    def title_bar(self, title):
        # simple title at the top
        self.fb.fill_rect(0, 0, self.fb.width, 10, 1)
        try:
            self.fb.text(title, 2, 2, 0)
        except TypeError:
            # some drivers use fb.text(x, y, string, color)
            self.fb.text(2, 2, title, 0)
