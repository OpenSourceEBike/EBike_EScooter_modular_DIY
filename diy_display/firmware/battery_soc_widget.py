# battery_soc_widget_mpy.py
# MicroPython version using framebuf (monochrome or RGB565).

import framebuf

BLACK = 0x0000
WHITE = 0xFFFF

class BatterySOCWidget:
    """
    Draws a battery outline and up to 5 SOC bars.
    Works with any object exposing framebuf-like methods:
      - pixel, line, rect, fill_rect
    """

    def __init__(self, fb: framebuf.FrameBuffer, display_width, display_height,
                 fg=WHITE, bg=BLACK):
        self.fb = fb
        self._d_width = display_width
        self._d_height = display_height
        self.fg = fg
        self.bg = bg

        # Bar geometry (mirrors your original)
        self.soc_bar_width = 8
        self.soc_bar_height = 11
        self.bar_x0 = 2
        self.bar_y0 = self._d_height - self.soc_bar_height - 2

        # Precompute rectangles for the 5 bars
        # bars 1..4 are full size; bar 5 is the small cap (narrower/shorter)
        self._bars = [
            # (x, y, w, h)
            (self.bar_x0 + (self.soc_bar_width + 1) * 0,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 1,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 2,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 3,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            # bar 5 (cap), width-2, height-6, y+3
            (self.bar_x0 + (self.soc_bar_width + 1) * 4,
             self.bar_y0 + 3, self.soc_bar_width - 2, self.soc_bar_height - 6),
        ]
        # tiny vertical tick next to bar 5 (your _fill_rectangle_5_1)
        self._bar5_tick = (
            self.bar_x0 + (self.soc_bar_width + 1) * 4 + self.soc_bar_width - 2,
            self.bar_y0 + 3 + 1,
            1,
            self.soc_bar_height - 6 - 2,
        )

        # Track last drawn states to avoid unnecessary redraws
        self._last_slots = [False] * 6  # indices 0..4 bars, 5 for the small tick

    # ---------------- drawing helpers ----------------
    def _draw_line(self, x0, y0, x1, y1, color):
        try:
            self.fb.line(x0, y0, x1, y1, color)
        except AttributeError:
            # fallback Bresenham if driver lacks .line()
            dx = abs(x1 - x0)
            sx = 1 if x0 < x1 else -1
            dy = -abs(y1 - y0)
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                self.fb.pixel(x0, y0, color)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy

    def _fill_rect(self, x, y, w, h, color):
        self.fb.fill_rect(x, y, w, h, color)

    # ---------------- public API ----------------
    def draw_contour(self):
        """Draw the battery outline (like your l1..l8)."""
        h = self._d_height
        # Original lines, translated directly:
        # l1: (0, h-1) -> (0, h-1-14)
        self._draw_line(0, h - 1, 0, h - 1 - 14, self.fg)
        # l2: (0, h-1-14) -> (34+4, h-1-14)
        self._draw_line(0, h - 1 - 14, 38, h - 1 - 14, self.fg)
        # l3: (38, h-1-14) -> (38, h-1-14+3)
        self._draw_line(38, h - 1 - 14, 38, h - 1 - 14 + 3, self.fg)
        # l4: (38, h-1-14+3) -> (38+6, h-1-14+3)
        self._draw_line(38, h - 1 - 14 + 3, 44, h - 1 - 14 + 3, self.fg)
        # l5_1 & l5_2 are single dots; we draw the vertical between (45,...) as l5
        # l5: (46, h-1-14+5) -> (46, h-1-14+5+4)
        self._draw_line(46, h - 1 - 14 + 5, 46, h - 1 - 14 + 9, self.fg)
        # l6: (44, h-1-14+11) -> (38, h-1-14+11)
        self._draw_line(44, h - 1 - 14 + 11, 38, h - 1 - 14 + 11, self.fg)
        # l7: (38, h-1-14+11) -> (38, h-1-14+14)
        self._draw_line(38, h - 1 - 14 + 11, 38, h - 1 - 14 + 14, self.fg)
        # l8: (38, h-1-14+14) -> (0, h-1-14+14)
        self._draw_line(38, h - 1 - 14 + 14, 0, h - 1 - 14 + 14, self.fg)

        # Optional: clear the bars region initially
        self.clear_bars()

    def clear_bars(self):
        """Erase the whole bars region."""
        # region spanning from first bar left to end of cap area
        x0 = self.bar_x0
        y0 = self.bar_y0
        total_w = (self.soc_bar_width + 1) * 4 + self.soc_bar_width + 6  # rough
        total_h = self.soc_bar_height + 2
        self._fill_rect(x0 - 1, y0 - 1, total_w + 2, total_h + 2, self.bg)
        self._last_slots = [False] * 6

    def update(self, battery_soc: int):
        """Update bars according to SOC thresholds."""
        # Clamp 0..100
        soc = 0 if battery_soc < 0 else 100 if battery_soc > 100 else battery_soc

        # Determine which bars should be on
        want = [
            soc >= 20,  # bar 1
            soc >= 40,  # bar 2
            soc >= 60,  # bar 3
            soc >= 80,  # bar 4
            soc >= 90,  # bar 5 (cap)
        ]
        want_tick = soc >= 90  # tiny vertical tick

        # Draw/erase bars 1..5
        for i, on in enumerate(want):
            x, y, w, h = self._bars[i]
            if on and not self._last_slots[i]:
                self._fill_rect(x, y, w, h, self.fg)
                self._last_slots[i] = True
            elif (not on) and self._last_slots[i]:
                self._fill_rect(x, y, w, h, self.bg)
                self._last_slots[i] = False

        # Draw/erase the small tick near bar 5
        xt, yt, wt, ht = self._bar5_tick
        if want_tick and not self._last_slots[5]:
            self._fill_rect(xt, yt, wt, ht, self.fg)
            self._last_slots[5] = True
        elif (not want_tick) and self._last_slots[5]:
            self._fill_rect(xt, yt, wt, ht, self.bg)
            self._last_slots[5] = False
