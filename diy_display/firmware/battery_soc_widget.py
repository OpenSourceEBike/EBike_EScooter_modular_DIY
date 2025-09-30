# battery_soc_widget_mpy.py
# Pixel-perfect MicroPython port of your CircuitPython battery widget.

import framebuf

BLACK = 0x0000
WHITE = 0xFFFF

# --- Hysteresis thresholds (percent) ---
# If a bar is OFF it turns ON when SOC >= bar_on[i]
# If a bar is ON  it turns OFF when SOC <= bar_off[i]
# Example: bar0: ON at 25%, OFF at 15% (your request)
_bar_on  = [25, 45, 65, 85, 92]   # bars 1..5 (cap is index 4)
_bar_off = [15, 35, 55, 75, 88]

# Tiny tick beside the cap (can be different if you want)
_tick_on  = 92
_tick_off = 88

class BatterySOCWidget:
    def __init__(self, fb: framebuf.FrameBuffer, display_width, display_height,
                 fg=WHITE, bg=BLACK):
        self.fb = fb
        self._w = display_width
        self._h = display_height
        self.fg = fg
        self.bg = bg

        # Bars geometry (same as CP)
        self.soc_bar_width  = 8
        self.soc_bar_height = 11
        self.bar_x0 = 2
        self.bar_y0 = self._h - self.soc_bar_height - 2  # = h - 13

        # Precomputed bar rectangles (x, y, w, h)
        self._bars = [
            (self.bar_x0 + (self.soc_bar_width + 1) * 0,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 1,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 2,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            (self.bar_x0 + (self.soc_bar_width + 1) * 3,
             self.bar_y0, self.soc_bar_width, self.soc_bar_height),
            # Cap bar (narrower/shorter, shifted down)
            (self.bar_x0 + (self.soc_bar_width + 1) * 4,
             self.bar_y0 + 3, self.soc_bar_width - 2, self.soc_bar_height - 6),
        ]
        # Tiny vertical tick beside the cap
        self._bar5_tick = (
            self.bar_x0 + (self.soc_bar_width + 1) * 4 + self.soc_bar_width - 2,
            self.bar_y0 + 3 + 1,
            1,
            self.soc_bar_height - 6 - 2,
        )

        self._last_slots = [False] * 6  # bars 0..4 + tick(5)

    # --- 1px segment helpers (inclusive endpoints) ---
    def _hseg(self, x0, x1, y, c):
        if x1 < x0:
            x0, x1 = x1, x0
        self.fb.fill_rect(int(x0), int(y), int(x1 - x0 + 1), 1, c)

    def _vseg(self, x, y0, y1, c):
        if y1 < y0:
            y0, y1 = y1, y0
        self.fb.fill_rect(int(x), int(y0), 1, int(y1 - y0 + 1), c)

    # --- public API ---
    def draw_contour(self):
        """Replicates your exact CP lines l1..l8 + l5_1/l5/l5_2."""
        h = self._h

        # l1
        self._vseg(0,            h - 1,          h - 1 - 14, self.fg)
        # l2
        self._hseg(0,            0 + 34 + 4,     h - 1 - 14, self.fg)
        # l3
        self._vseg(0 + 34 + 4,   h - 1 - 14,     h - 1 - 14 + 3, self.fg)
        # l4
        self._hseg(0 + 34 + 4,   0 + 34 + 4 + 6, h - 1 - 14 + 3, self.fg)
        # l5_1 (dot)
        self._vseg(0 + 34 + 4 + 7, h - 1 - 14 + 4, h - 1 - 14 + 4, self.fg)
        # l5 (vertical)
        self._vseg(0 + 34 + 4 + 8, h - 1 - 14 + 5, h - 1 - 14 + 5 + 4, self.fg)
        # l5_2 (dot)
        self._vseg(0 + 34 + 4 + 7, h - 1 - 14 + 5 + 5, h - 1 - 14 + 5 + 5, self.fg)
        # l6
        self._hseg(0 + 34 + 4 + 6, 0 + 34 + 4,   h - 1 - 14 + 3 + 8, self.fg)
        # l7
        self._vseg(0 + 34 + 4,   h - 1 - 14 + 3 + 8, h - 1 - 14 + 3 + 8 + 3, self.fg)
        # l8
        self._hseg(0 + 34 + 4,   0,              h - 1 - 14 + 3 + 8 + 3, self.fg)

        # Clear only the true interior so the outline never gets erased
        top    = h - 1 - 14
        bottom = h - 1 - 14 + 3 + 8 + 3
        self._clear_interior(1, top + 1, (0 + 34 + 4) - 1, bottom - 1)

        # Start with all bars off
        self._last_slots = [False] * 6

    def _clear_interior(self, x_left, y_top, x_right, y_bottom):
        """Clear inside the main battery body (keeps 1px outline)."""
        self.fb.fill_rect(x_left, y_top, x_right - x_left + 1,
                          y_bottom - y_top + 1, self.bg)

    def update(self, battery_soc: int):
        # Clamp 0..100
        soc = 0 if battery_soc < 0 else 100 if battery_soc > 100 else battery_soc

        # Decide desired state per bar using hysteresis
        # self._last_slots[i] holds current state (False=OFF, True=ON)
        for i in range(5):
            currently_on = self._last_slots[i]
            if not currently_on:
                # OFF -> consider turning ON
                want_on = soc >= _bar_on[i]
            else:
                # ON -> consider turning OFF
                want_on = not (soc <= _bar_off[i])

            # Draw/erase if state changed
            if want_on != currently_on:
                x, y, w, h = self._bars[i]
                self.fb.fill_rect(x, y, w, h, self.fg if want_on else self.bg)
                self._last_slots[i] = want_on

        # Tiny tick near the cap (index 5 in _last_slots)
        tick_on_now = self._last_slots[5]
        if not tick_on_now:
            tick_want_on = soc >= _tick_on
        else:
            tick_want_on = not (soc <= _tick_off)

        if tick_want_on != tick_on_now:
            xt, yt, wt, ht = self._bar5_tick
            self.fb.fill_rect(xt, yt, wt, ht, self.fg if tick_want_on else self.bg)
            self._last_slots[5] = tick_want_on
