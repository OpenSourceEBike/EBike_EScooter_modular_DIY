# warning_widget.py
import framebuf
from writer import Writer

class WidgetWarning:
    """
    Small warning text widget.
    - Draws at a fixed origin (x0, y0) using a provided font (e.g., FreeSans10).
    - Clears only the exact bounding box of the *previous* string before drawing the new one.
    - Skips work if the text hasn't changed.
    """

    def __init__(self, fb: framebuf.FrameBuffer, display_width: int, display_height: int,
                 x0: int = 0, y0: int = 40, fg=1, bg=0, font=None, baseline_adjust: int = 0):
        self.fb = fb
        self._w = display_width
        self._h = display_height
        self.fg = fg
        self.bg = bg
        self.font = font
        self.x0 = x0
        self.y0 = y0
        self._baseline_adjust = baseline_adjust  # tweak if your font sits low/high

        # Writer for this font
        self._writer = Writer(self.fb, self.font, verbose=False)
        self._writer.set_clip(row_clip=True, col_clip=True, wrap=False)

        # Track last draw to clear only what changed
        self._last_text = ""
        self._last_w = 0
        self._last_h = 0

    # ---------- helpers ----------
    def _text_width(self, s: str) -> int:
        w = 0
        for ch in s:
            _, _, cw = self.font.get_ch(ch)
            w += cw
        return w

    # ---------- public ----------
    def clear(self):
        """Clear only the previous text's bounding box."""
        if self._last_text:
            self.fb.fill_rect(self.x0, max(0, self.y0 + self._baseline_adjust),
                              self._last_w, self._last_h, self.bg)
            self._last_text = ""
            self._last_w = 0
            self._last_h = 0

    def update(self, msg: str):
        """
        Draw a small warning string at (x0, y0).
        Clears only the previously drawn string's bounding box first.
        """
        # No change? skip
        if msg == self._last_text:
            return

        # 1) Clear exactly the old text box
        self.clear()

        # 2) Draw new text (if any)
        if msg:
            h = self.font.height()
            w = self._text_width(msg)

            y_draw = max(0, self.y0 + self._baseline_adjust)
            # Clip into display bounds just in case
            if self.x0 + w > self._w:
                w = max(0, self._w - self.x0)

            Writer.set_textpos(self.fb, y_draw, self.x0)  # (row, col)
            self._writer.printstring(msg)

            # Save bounding box for next clear
            self._last_text = msg
            self._last_w = w
            self._last_h = h
