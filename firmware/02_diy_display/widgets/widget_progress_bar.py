# widgets/widget_progress_bar.py
# Simple progress bar widget (outline + filled interior) with optional label.

from widgets.widget_text_box import WidgetTextBox

BLACK = 1
WHITE = 0


class ProgressBarWidget:
    def __init__(
        self,
        fb,
        x=0,
        y=0,
        width=100,
        height=12,
        fg=BLACK,
        bg=WHITE,
        label_text=None,
        label_font=None,
        label_gap=1,
        label_dy=0,
        label_align="right",
    ):
        self.fb = fb
        self.x = int(x)
        self.y = int(y)
        self.w = int(width)
        self.h = int(height)
        self.fg = fg
        self.bg = bg
        self.visible = True
        self._last_fill_w = None
        self._label = None
        self._label_text = None

        if label_text and label_font:
            self._label_text = str(label_text)
            self._label = WidgetTextBox(
                self.fb,
                self.fb.width,
                self.fb.width,
                font=label_font,
                x=self.x - int(label_gap),
                y=self.y + int(label_dy),
                anchor="topright",
                pattern=self._label_text,
                align_inside=label_align,
            )

    def set_visible(self, visible: bool, clear: bool = True):
        visible = bool(visible)
        if visible == self.visible:
            return
        if not visible and clear:
            self.fb.fill_rect(self.x, self.y, self.w, self.h, self.bg)
            if self._label:
                self._label.hide(clear=True)
        self.visible = visible
        if self._label:
            self._label.set_visible(visible, clear=clear)

    def draw_contour(self):
        if not self.visible:
            return
        self.fb.rect(self.x, self.y, self.w, self.h, self.fg)
        if self.w > 2 and self.h > 2:
            self.fb.fill_rect(self.x + 1, self.y + 1, self.w - 2, self.h - 2, self.bg)
        self._last_fill_w = 0
        if self._label and self._label_text is not None:
            self._label.update(self._label_text)

    def set_label_text(self, text):
        if not self._label:
            return
        self._label_text = "" if text is None else str(text)
        self._label.pattern = self._label_text
        if self.visible:
            self._label.update(self._label_text)

    def update(self, percent):
        if not self.visible:
            return
        try:
            p = int(percent)
        except Exception:
            p = 0
        if p < 0:
            p = 0
        elif p > 100:
            p = 100

        if self.w <= 2 or self.h <= 2:
            return

        inner_w = self.w - 2
        fill_w = (inner_w * p) // 100
        if self._last_fill_w is None:
            self._last_fill_w = 0

        if fill_w == self._last_fill_w:
            return

        if fill_w > self._last_fill_w:
            dx = self._last_fill_w
            self.fb.fill_rect(self.x + 1 + dx, self.y + 1, fill_w - dx, self.h - 2, self.fg)
        else:
            dx = fill_w
            self.fb.fill_rect(self.x + 1 + dx, self.y + 1, self._last_fill_w - dx, self.h - 2, self.bg)
        self._last_fill_w = fill_w
