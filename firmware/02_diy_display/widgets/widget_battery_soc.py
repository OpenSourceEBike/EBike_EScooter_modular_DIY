# widgets/widget_battery_soc.py
# Battery SOC widget with (x, y), 1x/2x scaling, and integrated blinking.
# - Blinks the last active bar while charging
# - If NO bar is active, the OUTLINE blinks (even if charging is OFF)

import framebuf, time

BLACK = 0x0000
WHITE = 0xFFFF

# Hysteresis thresholds (percent) for 4 tall bars + cap (index 4)
_BAR_ON  = [20, 40, 60, 80, 90]
_BAR_OFF = [10, 30, 50, 70, 80]


class BatterySOCWidget:
    # Base geometry (unscaled)
    _BODY_W = 38
    _BODY_H = 14
    _CAP_W  = 6

    def __init__(self, fb: framebuf.FrameBuffer,
                 x: int = 0, y: int = 0, scale: int = 1,
                 fg=WHITE, bg=BLACK):
        if scale not in (1, 2):
            raise ValueError("scale must be 1 or 2")
        self.fb, self.fg, self.bg = fb, fg, bg
        self.x, self.y = int(x), int(y)
        self.scale = int(scale)

        self.total_width  = (self._BODY_W + 9) * self.scale   # +9 for cap + dots/line
        self.total_height = 15 * self.scale

        # Bars (already scaled, in pixel-space)
        self.soc_bar_width  = 8 * self.scale
        self.soc_bar_height = 11 * self.scale
        self._bar_x0 = self.x + 2 * self.scale
        self._bar_y0 = self.y + 2 * self.scale

        self._recompute_bar_rects()

        # Visibility
        self.visible = True
        self._current_soc = 0  # remember last SOC even when hidden

        # Runtime states (5 bars + tick)
        self._last_slots = [False] * 6
        self._last_soc   = None

        # Blink state (bar blink)
        self._charging_enabled = False
        self._blink_ton = 300
        self._blink_toff = 300
        self._blink_last_idx = None   # bar index (0..4)
        self._blink_visible = True
        self._blink_t0 = time.ticks_ms()

        # Outline blink (used when no bar is active)
        self._outline_visible = True
        self._outline_t0 = time.ticks_ms()

        # Track previous frame state: did we have any active bars?
        self._had_active_bar = False

    # ---------- visibility API ----------
    def set_visible(self, visible: bool, clear: bool = True):
        """
        Toggle widget visibility.
        - When turning OFF and clear=True, the area is cleared to bg.
        - When turning ON, the widget is fully redrawn using the last SOC.
        """
        visible = bool(visible)
        if visible == self.visible:
            return

        if not visible:
            # Going hidden: optionally clear the full bounding box
            if clear:
                self.fb.fill_rect(self.x, self.y, self.total_width, self.total_height, self.bg)
            # Pause visuals by just marking invisible; logic still tracks SOC
            self.visible = False
        else:
            # Going visible: redraw fresh
            self.visible = True
            self.draw_contour()
            # Force a full bar recompute on next update
            prev_soc = self._current_soc
            self._last_soc = None
            self.update(prev_soc)

    def hide(self, clear: bool = True):
        self.set_visible(False, clear=clear)

    def show(self):
        self.set_visible(True, clear=False)

    def is_visible(self) -> bool:
        return self.visible

    # ---------- positioning ----------
    def move_to(self, x: int, y: int):
        self.x, self.y = int(x), int(y)
        self._bar_x0 = self.x + 2 * self.scale
        self._bar_y0 = self.y + 2 * self.scale
        self._recompute_bar_rects()

    # ---------- low-level helpers ----------
    def _hseg_px(self, x0, x1, y, c, h=1):
        """Horizontal segment in pixel space; vertical thickness = h px."""
        if x1 < x0: x0, x1 = x1, x0
        self.fb.fill_rect(int(x0), int(y), int(x1 - x0 + 1), int(h), c)

    def _vseg_px(self, x, y0, y1, c, w=None):
        """Vertical segment in pixel space; horizontal thickness = w px."""
        if y1 < y0: y0, y1 = y1, y0
        if w is None: w = self.scale
        self.fb.fill_rect(int(x), int(y0), int(w), int(y1 - y0 + 1), c)

    def _recompute_bar_rects(self):
        s = self.scale; w = self.soc_bar_width; h = self.soc_bar_height
        # Four tall bars
        self._bars = [
            (self._bar_x0 + (w + 1*s)*i, self._bar_y0, w, h)
            for i in range(4)
        ]
        # Cap (narrower/shorter, shifted down)
        self._bars.append((
            self._bar_x0 + (w + 1*s)*4,
            self._bar_y0 + 3*s,
            w - 2*s,
            h - 6*s
        ))
        # Tiny vertical tick next to the cap
        self._bar5_tick = (
            self._bar_x0 + (w + 1*s)*4 + w - 2*s,
            self._bar_y0 + 4*s,
            1*s,
            h - 8*s
        )

    # ---------- outline drawing ----------
    def _draw_outline(self, on: bool):
        """Draw/erase the battery outline only (no interior clear)."""
        if not self.visible:
            return
        l, t, s = self.x, self.y, self.scale
        col = self.fg if on else self.bg
        h = 2 if s > 1 else 1   # single pixel at scale=1, double at scale=2

        # Symmetric cap geometry for both scales
        cap_top_y = t + 3 * s
        cap_bottom_y = t + self._BODY_H * s - 3 * s

        # Left side and top
        self._vseg_px(l, t + self._BODY_H * s, t, col)                             # l1
        self._hseg_px(l, l + self._BODY_W * s, t, col, h=h)                        # l2

        # Right joint up + cap top
        self._vseg_px(l + self._BODY_W * s, t, cap_top_y, col)                     # l3
        self._hseg_px(l + self._BODY_W * s,
                      l + (self._BODY_W + self._CAP_W) * s,
                      cap_top_y, col, h=h)                                         # l4

        # dots/line at the far right (ornamental)
        self._vseg_px(l + (self._BODY_W + 7) * s, t + 4 * s,  t + 4 * s + 1, col)
        self._vseg_px(l + (self._BODY_W + 8) * s, t + 5 * s,  t + 9 * s,     col)
        self._vseg_px(l + (self._BODY_W + 7) * s, t + 10 * s, t + 10 * s + 1, col)

        # Cap bottom + right joint down
        self._hseg_px(l + (self._BODY_W + self._CAP_W) * s,
                      l + self._BODY_W * s,
                      cap_bottom_y, col, h=h)                                      # l6
        self._vseg_px(l + self._BODY_W * s, cap_bottom_y, t + self._BODY_H * s, col)  # l7

        # Bottom
        self._hseg_px(l + self._BODY_W * s, l, t + self._BODY_H * s, col, h=h)     # l8

    # ---------- public: draw full widget outline and clear interior ----------
    def draw_contour(self):
        """Draw the outline at (x, y) and clear the interior (keeps 1px*scale border)."""
        if not self.visible:
            return
        l, t, s = self.x, self.y, self.scale

        # Outline ON
        self._draw_outline(True)

        # Clear interior of the body (preserves 1px*scale border)
        ix = l + 1*s; iy = t + 1*s
        iw = (self._BODY_W - 2)*s; ih = (self._BODY_H - 2)*s
        self.fb.fill_rect(ix, iy, iw, ih, self.bg)

        # Reset states (do NOT redraw any bar here)
        self._last_slots = [False]*6
        self._last_soc = None

        # Reset blink states so no bar gets redrawn spuriously
        self._blink_last_idx = None
        self._blink_visible = True
        self._blink_t0 = time.ticks_ms()

        # Ensure outline is visible initially
        self._outline_visible = True
        self._outline_t0 = time.ticks_ms()

        # Also reset "had active bar" tracker
        self._had_active_bar = False

    # ---------- helper: deterministic redraw of current state ----------
    def _redraw_current_state(self):
        """Clears bbox, draws outline ON, then draws bars/tick according to _last_slots."""
        if not self.visible:
            return
        # Full clear
        self.fb.fill_rect(self.x, self.y, self.total_width, self.total_height, self.bg)
        # Fresh contour
        self.draw_contour()
        # Repaint bars and tick as per logical state
        for i in range(5):
            if self._last_slots[i]:
                x, y, w, h = self._bars[i]
                self.fb.fill_rect(x, y, w, h, self.fg)
        if self._last_slots[5]:
            xt, yt, wt, ht = self._bar5_tick
            self.fb.fill_rect(xt, yt, wt, ht, self.fg)

    # ---------- main logic ----------
    def update(self, soc: int):
        """Update bars/tick with hysteresis and run blinking logic."""
        soc = max(0, min(100, int(soc)))
        self._current_soc = soc
        if not self.visible:
            return

        # --- Hard-clear path when truly empty (fixes ghost bars on big drops) ---
        if soc == 0 and any(self._last_slots):
            for i in range(5):
                if self._last_slots[i]:
                    x, y, w, h = self._bars[i]
                    self.fb.fill_rect(x, y, w, h, self.bg)
                    self._last_slots[i] = False
            if self._last_slots[5]:
                xt, yt, wt, ht = self._bar5_tick
                self.fb.fill_rect(xt, yt, wt, ht, self.bg)
                self._last_slots[5] = False
            # No bar should be considered a blink target now
            self._blink_last_idx = None
            self._blink_visible = True

        if soc != self._last_soc:
            self._last_soc = soc
            # Bars 0..4 (with hysteresis)
            for i in range(5):
                on = self._last_slots[i]
                want_on = soc >= _BAR_ON[i] if not on else not (soc <= _BAR_OFF[i])
                if want_on != on:
                    x, y, w, h = self._bars[i]
                    self.fb.fill_rect(x, y, w, h, self.fg if want_on else self.bg)
                    self._last_slots[i] = want_on
            # Tick shares thresholds with cap (index 4)
            tick_on = self._last_slots[5]
            want_tick = soc >= _BAR_ON[4] if not tick_on else not (soc <= _BAR_OFF[4])
            if want_tick != tick_on:
                xt, yt, wt, ht = self._bar5_tick
                self.fb.fill_rect(xt, yt, wt, ht, self.fg if want_tick else self.bg)
                self._last_slots[5] = want_tick
            # SOC change may shift the blinking target
            self._ensure_blink_target_after_soc_change()

        # Decide blinking mode:
        last_idx = self._find_last_on_bar()

        if last_idx is None:
            # EMPTY: no active bars -> blink outline
            self._blink_last_idx = None     # guard: never restore any bar
            self._blink_visible = True

            if self._had_active_bar:
                # Transitioned from non-empty to empty: reset phase
                self._outline_visible = True
                self._outline_t0 = time.ticks_ms()
            if self._outline_t0 is None:
                self._outline_visible = True
                self._outline_t0 = time.ticks_ms()
            self._animate_outline()
            self._had_active_bar = False

        else:
            # NON-EMPTY
            if not self._had_active_bar:
                # ***** KEY FIX: FULL REDRAW on empty→non-empty transition *****
                # Garante que não ficam segmentos do contorno apagados por causa do blink.
                self._redraw_current_state()
            else:
                # As we remain non-empty, just ensure outline is ON if it was off.
                self._restore_outline()

            self._had_active_bar = True

            if self._charging_enabled:
                self._animate_blink_bar()
            else:
                self._restore_blink_bar()

    # ---------- charging / timing API ----------
    def set_charging(self, enabled: bool):
        """Enable/disable bar blinking. Outline blinking when empty is always allowed."""
        self._charging_enabled = bool(enabled)
        if not enabled and self.visible:
            self._restore_blink_bar()
        now = time.ticks_ms()
        self._blink_t0 = now
        if self._find_last_on_bar() is None:
            self._outline_t0 = now  # seed outline if empty

    def set_blink_timing(self, ton_ms: int, toff_ms: int):
        """Set blink ON/OFF durations (ms). Applies to both bar and outline blinking."""
        self._blink_ton = max(0, int(ton_ms))
        self._blink_toff = max(0, int(toff_ms))

    # ---------- blink helpers (BAR) ----------
    def _find_last_on_bar(self):
        for i in range(4, -1, -1):
            if self._last_slots[i]:
                return i
        return None

    def _animate_blink_bar(self):
        if not self.visible:
            return
        idx = self._find_last_on_bar()
        if idx is None:
            self._blink_last_idx = None
            self._blink_visible = True
            return

        if self._blink_last_idx is not None and self._blink_last_idx != idx:
            self._restore_blink_bar()
            self._blink_visible = True
            self._blink_t0 = time.ticks_ms()

        self._blink_last_idx = idx
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._blink_t0)

        if self._blink_visible:
            if elapsed >= self._blink_ton:
                self._draw_bar(idx, False)
                self._blink_visible = False
                self._blink_t0 = now
        else:
            if elapsed >= self._blink_toff:
                self._draw_bar(idx, True)
                self._blink_visible = True
                self._blink_t0 = now

    def _draw_bar(self, i: int, on: bool):
        if not self.visible:
            return
        x, y, w, h = self._bars[i]
        self.fb.fill_rect(x, y, w, h, self.fg if on else self.bg)
        if i == 4:
            xt, yt, wt, ht = self._bar5_tick
            self.fb.fill_rect(xt, yt, wt, ht, self.fg if on else self.bg)

    def _restore_blink_bar(self):
        """
        If a bar is hidden due to blinking, restore it — but ONLY if that bar
        is still logically ON. This prevents 'ghost' redraw after SOC drops.
        """
        if not self.visible:
            return
        if self._blink_last_idx is not None and not self._blink_visible:
            idx = self._blink_last_idx
            if 0 <= idx < 5 and self._last_slots[idx]:
                self._draw_bar(idx, True)
            # Either way, stop hiding
            self._blink_visible = True
            # If it wasn't logically on, also drop the target
            if idx is not None and (idx < 0 or idx > 4 or not self._last_slots[idx]):
                self._blink_last_idx = self._find_last_on_bar()

    def _ensure_blink_target_after_soc_change(self):
        """Keep blink state consistent after SOC changes."""
        if not self.visible:
            return
        idx = self._find_last_on_bar()
        if idx != self._blink_last_idx:
            # If previous blink bar was hidden, restore only if still on
            self._restore_blink_bar()
            self._blink_last_idx = idx
            self._blink_visible = True

    # ---------- blink helpers (OUTLINE when empty) ----------
    def _animate_outline(self):
        if not self.visible:
            return
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._outline_t0)

        if self._outline_visible:
            if elapsed >= self._blink_ton:
                self._draw_outline(False)
                self._outline_visible = False
                self._outline_t0 = now
        else:
            if elapsed >= self._blink_toff:
                self._draw_outline(True)
                self._outline_visible = True
                self._outline_t0 = now

    def _restore_outline(self):
        """Ensure the outline is visible (used when bars exist)."""
        if not self.visible:
            return
        if not self._outline_visible:
            self._draw_outline(True)
            self._outline_visible = True

    # ---------- public helper ----------
    def count_active_bars(self, include_tick: bool = False) -> int:
        """
        Return how many bars are currently ON.
        If include_tick=True, includes the small tick next to the cap (index 5).
        """
        n = 6 if include_tick else 5
        return sum(1 for on in self._last_slots[:n] if on)
