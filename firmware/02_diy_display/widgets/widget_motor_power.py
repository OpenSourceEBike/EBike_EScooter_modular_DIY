# widget_motor_power.py (FAST + SOLID + PROPORTIONAL PROGRESS)
# - Arc fills strictly from 180° (left) to up to 270° (up) on a 0..360° (Y-down) axis.
# - Analytic scanlines for solid fill (no per-pixel atan2, no oversampling).
# - Minimal clearing on updates, with a hard clear on the first frame.
# - Progress is proportional to the total path length (arc midline + top bar).
# - Top bar grows to the right after the arc completes.
# - Supports X/Y offsets for nudging.

import math

BLACK = 1
WHITE = 0

# Mesh size in pixels for negative (regen) fill. Min 1, max 10.
MESH_SIZE = 2
# Regen thickness scale for both arc and bar.
REGEN_THICKNESS_SCALE = 0.6

def map_value(x, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    x = max(min(x, in_max), in_min)
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

# -------- Layout --------
motor_power_width  = 26
motor_power_height = 18
motor_power_x      = 2
motor_power_y      = 0

# -------- Ring geometry --------
ARC_CX, ARC_CY = 36, 36
ARC_R_OUT      = 37
ARC_WIDTH      = 19
ARC_R_IN       = ARC_R_OUT - ARC_WIDTH

# Optional offsets
ARC_X_OFFSET = 2
ARC_Y_OFFSET = 0

# Angles (Y-down)  right=0°, down=90°, left=180°, up=270°
ARC_LEFT_DEG = 180.0
ARC_UP_DEG   = 270.0

# --- Proportional mapping helpers (arc vs bar) ---
def _arc_midline_length():
    # Use the arc midline length as a proxy for perceptual path length
    r_avg = 0.5 * (ARC_R_IN + ARC_R_OUT)
    return r_avg * (math.pi * 0.5)  # 90 degrees = π/2

def _progress_break_percent():
    L_arc = _arc_midline_length()
    L_bar = motor_power_width
    return 100.0 * L_arc / (L_arc + L_bar)

class MotorPowerWidget:
    def __init__(self, fb, display_width, display_height):
        self.fb = fb
        self.dw = display_width
        self.dh = display_height
        self._prev_rect_w = -1
        self._prev_A_end  = None
        self._prev_negative = None
        self._has_hline = hasattr(self.fb, "hline")
        self._has_vline = hasattr(self.fb, "vline")
        self._first_frame_cleared = False

    # ---- tiny gfx helpers ----
    def _line(self, x0, y0, x1, y1, c=WHITE):
        self.fb.line(int(x0), int(y0), int(x1), int(y1), c)

    def _hline(self, x, y, w, c=WHITE):
        if w <= 0:
            return
        if self._has_hline:
            self.fb.hline(int(x), int(y), int(w), c)
        else:
            self._line(int(x), int(y), int(x + w - 1), int(y), c)

    def _vline(self, x, y, h, c=WHITE):
        if h <= 0:
            return
        if self._has_vline:
            self.fb.vline(int(x), int(y), int(h), c)
        else:
            self._line(int(x), int(y), int(x), int(y + h - 1), c)

    def _rect(self, x, y, w, h, c=WHITE, fill=False):
        if fill:
            self.fb.fill_rect(int(x), int(y), int(w), int(h), c)
        else:
            self.fb.rect(int(x), int(y), int(w), int(h), c)

    def _mesh_step(self, step):
        if step is None:
            step = MESH_SIZE
        step = int(step)
        if step < 1:
            step = 1
        elif step > 10:
            step = 10
        return step

    def _mesh_on(self, x, y, step):
        period = step * 2
        return ((x + y) % period) < step or ((x - y) % period) < step

    # ---- areas to clear / force black underneath ----
    def _clear_bucket(self):
        self._rect(motor_power_x + motor_power_width + 9,
                   motor_power_y, motor_power_width, motor_power_height + 1,
                   WHITE, fill=True)

    def _clear_wedge_bbox(self):
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET
        x0 = int(cx - ARC_R_OUT)
        y0 = int(cy - ARC_R_OUT)
        w  = int(ARC_R_OUT) + 1
        h  = int(ARC_R_OUT) + 1
        self._rect(x0, y0, w, h, WHITE, fill=True)

    def _hard_clear_internals(self):
        self._clear_wedge_bbox()
        self._clear_bucket()

    # ---- outlines ----
    def _draw_bucket_outline(self):
        # Rectangular outline for the top bar
        s_y = 0
        w   = 62
        w2  = w // 2
        xL  = w2 + 5
        xR  = w
        yT  = s_y + 0
        yB  = s_y + 18

        # top and bottom
        self._hline(xL, yB, (xR - xL + 1), BLACK)
        self._hline(xL, yT, (xR - xL + 1), BLACK)
        # sides (closed bucket)
        self._vline(xR, yT, (yB - yT + 1), BLACK)

    def _draw_arc_outlines(self):
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET

        def poly_arc(r):
            prev = None
            # degree-by-degree polyline for crisp outline
            for a in range(int(ARC_LEFT_DEG), int(ARC_UP_DEG) + 1):
                rad = math.radians(a)
                x = int(cx + r * math.cos(rad))
                y = int(cy + r * math.sin(rad))  # Y-down
                if prev:
                    self._line(prev[0], prev[1], x, y, BLACK)
                prev = (x, y)

        # Inner and outer arcs
        poly_arc(ARC_R_IN)
        poly_arc(ARC_R_OUT)

        # Close the sector base with a horizontal line (y = cy)
        x_outer = int(cx - ARC_R_OUT)
        x_inner = int(cx - ARC_R_IN)
        self._hline(x_outer, cy, (x_inner - x_outer + 1), BLACK)

        # Ensure the outermost base pixel (rounding safety)
        self.fb.pixel(x_outer, cy, BLACK)

    # -------- ring fill via scanlines --------
    def _fill_wedge_scanlines(self, A_end_deg, color):
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET

        A = float(A_end_deg)
        if A < ARC_LEFT_DEG:  A = ARC_LEFT_DEG
        if A > ARC_UP_DEG:    A = ARC_UP_DEG
        Arad = math.radians(A)

        r_out2 = ARC_R_OUT * ARC_R_OUT
        r_in2  = ARC_R_IN  * ARC_R_IN

        tanA = math.tan(Arad)
        tiny = 1e-6

        y_min = cy - ARC_R_OUT
        y_max = cy

        for y in range(y_min, y_max + 1):
            dy = y - cy
            dy2 = dy * dy
            if dy2 > r_out2:
                continue

            # outer circle intersection (left)
            x_out = math.sqrt(r_out2 - dy2)
            x_left = int(math.floor(cx - x_out))

            # inner circle intersection (left), when it exists
            if dy2 <= r_in2:
                x_in = math.sqrt(r_in2 - dy2)
                x_inner_edge = cx - x_in
            else:
                x_inner_edge = float('inf')  # no inner limit on this row

            # angle boundary
            if abs(tanA) > tiny:
                dx_ang = dy / tanA      # dx negative for this sector
                x_angle_edge = cx + dx_ang
            else:
                x_angle_edge = -1e9     # A ≈ 180°, include full left annulus

            x_right_f = min(x_inner_edge, x_angle_edge)
            x_right = int(math.floor(x_right_f))

            if x_right >= x_left:
                self._hline(x_left, y, x_right - x_left + 1, color)

    def _fill_wedge_scanlines_dither(self, A_end_deg, color, step=None, thickness_scale=1.0):
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET
        step = self._mesh_step(step)

        A = float(A_end_deg)
        if A < ARC_LEFT_DEG:  A = ARC_LEFT_DEG
        if A > ARC_UP_DEG:    A = ARC_UP_DEG
        Arad = math.radians(A)

        thickness_scale = float(thickness_scale)
        if thickness_scale < 0.1:
            thickness_scale = 0.1
        if thickness_scale > 1.0:
            thickness_scale = 1.0

        r_mid = 0.5 * (ARC_R_IN + ARC_R_OUT)
        half_th = 0.5 * (ARC_R_OUT - ARC_R_IN) * thickness_scale
        r_out = r_mid + half_th
        r_in = max(0.0, r_mid - half_th)
        r_out2 = r_out * r_out
        r_in2  = r_in  * r_in

        tanA = math.tan(Arad)
        tiny = 1e-6

        y_min = cy - ARC_R_OUT
        y_max = cy

        for y in range(y_min, y_max + 1):
            dy = y - cy
            dy2 = dy * dy
            if dy2 > r_out2:
                continue

            # outer circle intersection (left)
            x_out = math.sqrt(r_out2 - dy2)
            x_left = int(math.floor(cx - x_out))

            # inner circle intersection (left), when it exists
            if dy2 <= r_in2:
                x_in = math.sqrt(r_in2 - dy2)
                x_inner_edge = cx - x_in
            else:
                x_inner_edge = float('inf')  # no inner limit on this row

            # angle boundary
            if abs(tanA) > tiny:
                dx_ang = dy / tanA      # dx negative for this sector
                x_angle_edge = cx + dx_ang
            else:
                x_angle_edge = -1e9     # A ~ 180 deg, include full left annulus

            x_right_f = min(x_inner_edge, x_angle_edge)
            x_right = int(math.floor(x_right_f))

            if x_right >= x_left:
                for x in range(x_left, x_right + 1):
                    if self._mesh_on(x, y, step):
                        self.fb.pixel(x, y, color)

    def _rect_dither(self, x, y, w, h, c=WHITE, step=None):
        if w <= 0 or h <= 0:
            return
        x0 = int(x)
        y0 = int(y)
        step = self._mesh_step(step)
        for yy in range(y0, y0 + int(h)):
            for xx in range(x0, x0 + int(w)):
                if self._mesh_on(xx, yy, step):
                    self.fb.pixel(xx, yy, c)

    # ---- public API ----
    def draw_contour(self):
        # Ensure a clean background underneath on first call
        if not self._first_frame_cleared:
            self._hard_clear_internals()
            self._first_frame_cleared = True
        self._draw_bucket_outline()
        self._draw_arc_outlines()
        self._prev_A_end  = ARC_LEFT_DEG
        self._prev_rect_w = -9999

    def update(self, motor_power_percent):
        negative = motor_power_percent < 0
        # Clamp 0..100 on magnitude
        p = int(max(0, min(100, abs(motor_power_percent))))

        # first-frame safety
        if not self._first_frame_cleared:
            self._hard_clear_internals()
            self._first_frame_cleared = True
            self._prev_negative = negative
        elif self._prev_negative is None:
            self._prev_negative = negative
        elif self._prev_negative != negative:
            # mode switch (solid <-> dither), force a clean redraw
            self._hard_clear_internals()
            self._prev_A_end = None
            self._prev_rect_w = -9999
            self._prev_negative = negative

        # ----- proportional mapping between arc and bar -----
        P_BREAK = _progress_break_percent()  # typically ~62% with current geometry

        # --- ARC segment (0 .. P_BREAK %) ---
        if p <= P_BREAK:
            if p == 0:
                # clear any previous wedge
                if self._prev_A_end is not None and self._prev_A_end != ARC_LEFT_DEG:
                    self._fill_wedge_scanlines(self._prev_A_end, WHITE)
                self._prev_A_end = ARC_LEFT_DEG
                self._draw_arc_outlines()
            else:
                t = p / P_BREAK if P_BREAK > 0 else 0.0
                A_end = ARC_LEFT_DEG + 90.0 * t  # 180 → 270
                if self._prev_A_end is not None and A_end != self._prev_A_end:
                    self._fill_wedge_scanlines(self._prev_A_end, WHITE)
                if negative:
                    self._fill_wedge_scanlines_dither(A_end, BLACK, thickness_scale=REGEN_THICKNESS_SCALE)
                else:
                    self._fill_wedge_scanlines(A_end, BLACK)
                self._draw_arc_outlines()
                self._prev_A_end = A_end
            rect_w = 0  # bar stays empty up to break

        # --- BAR segment (P_BREAK .. 100 %) ---
        else:
            # ensure arc is fully filled
            if self._prev_A_end is None or self._prev_A_end != ARC_UP_DEG:
                if self._prev_A_end is not None:
                    self._fill_wedge_scanlines(self._prev_A_end, WHITE)
                if negative:
                    self._fill_wedge_scanlines_dither(ARC_UP_DEG, BLACK, thickness_scale=REGEN_THICKNESS_SCALE)
                else:
                    self._fill_wedge_scanlines(ARC_UP_DEG, BLACK)
                self._draw_arc_outlines()
                self._prev_A_end = ARC_UP_DEG

            # map remaining progress to bar width
            if P_BREAK < 100.0:
                t_bar = (p - P_BREAK) / (100.0 - P_BREAK)
            else:
                t_bar = 0.0
            rect_w = int(round(t_bar * motor_power_width))

        # ---- draw/clear the top bar interior ----
        if rect_w != self._prev_rect_w:
            self._clear_bucket()
            if rect_w > 0:
                if negative:
                    regen_h = max(1, int(round((motor_power_height + 1) * REGEN_THICKNESS_SCALE)))
                    regen_y = motor_power_y + ((motor_power_height + 1 - regen_h) // 2)
                    self._rect_dither(motor_power_x + motor_power_width + 9,
                                      regen_y, rect_w, regen_h,
                                      BLACK)
                else:
                    self._rect(motor_power_x + motor_power_width + 9,
                               motor_power_y, rect_w, motor_power_height + 1,
                               BLACK, fill=True)
            self._draw_bucket_outline()
            self._prev_rect_w = rect_w

        # keep bucket outline crisp
        self._draw_bucket_outline()
