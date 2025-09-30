# wheel_speed_widget.py
import framebuf
from writer import Writer

class WidgetWheelSpeed:
    """
    Ultra-compact 2-digit speed display (top-right), right-aligned to the glass.
    - Clears only a fixed 2-digit bounding box (no full-height wiping).
    - No padding: flush to the right and top edges.
    - Only redraws when the value changes.
    """

    def __init__(self, fb: framebuf.FrameBuffer, display_width: int, display_height: int,
                 fg=1, bg=0, font=None):
        self.fb = fb
        self._w = display_width
        self._h = display_height
        self.fg = fg
        self.bg = bg
        self.font = font

        # Writer for the big font
        self._writer = Writer(self.fb, self.font, verbose=False)
        self._writer.set_clip(row_clip=True, col_clip=True, wrap=False)

        # Anchor at the top-right-most pixel on the glass
        self.anchor_x = self._w - 1   # e.g., 127 on a 128px-wide LCD
        self.anchor_y = 0             # top row

        # Compute worst-case 2-digit size using "88"
        self._max_w = self._text_width("88")
        self._max_h = self.font.height()

        # No padding requested
        self._pad_x = 0
        self._pad_y = 0

        # Writer baseline adjustment (depends on font; -2 works for freesansbold50)
        self._baseline_adjust = -2

        # Precompute the fixed 2-digit clear box (inclusive to the right edge)
        self._box_x = (self.anchor_x - self._max_w + 1) - self._pad_x
        if self._box_x < 0:
            self._box_x = 0
        self._box_y = max(0, self.anchor_y + self._pad_y + self._baseline_adjust)
        self._box_w = self._max_w + self._pad_x * 2
        self._box_h = self._max_h + self._pad_y * 2

        self._last_txt = None

    # ---------- helpers ----------
    def _text_width(self, s: str) -> int:
        w = 0
        for ch in s:
            _, _, cw = self.font.get_ch(ch)
            w += cw
        return w

    # ---------- public ----------
    def update(self, value_int: int):
        """Draw a 2-digit speed value, right-aligned to the top-right corner."""
        # clamp to 0..99 for 2-digit mode
        if value_int < 0:
            value_int = 0
        elif value_int > 99:
            value_int = 99

        txt = f"{value_int:d}"
        if len(txt) > 2:
            txt = txt[-2:]

        # Skip if unchanged
        if txt == self._last_txt:
            return
        self._last_txt = txt

        # Clear only the fixed 2-digit box
        self.fb.fill_rect(self._box_x, self._box_y, self._box_w, self._box_h, self.bg)

        # Right-align inside the box so the last column used is exactly anchor_x
        w_txt = self._text_width(txt)
        x_txt = self.anchor_x - w_txt + 1
        if x_txt < 0:
            x_txt = 0
        if x_txt + w_txt > self._w:
            x_txt = self._w - w_txt

        # Lift baseline so glyphs hug the top
        y_txt = max(0, self.anchor_y + self._pad_y + self._baseline_adjust)

        Writer.set_textpos(self.fb, y_txt, x_txt)  # (row, col)
        self._writer.printstring(txt)
