# motor_power_widget_mpy.py (FAST + SOLID + MINIMAL CLEAR)
# - Arc fills strictly from 180° (left) to up to 270° (up) on a 0..360° (Y-down) system.
# - Analytic scanlines for solid fill (no atan2 per pixel, no oversampling).
# - Minimal clearing: erase only the previously drawn wedge lines.
# - Top bar (50..100%) grows to the right; outline always preserved.
# - Supports X/Y offsets for easy nudging.

import math

BLACK = 0
WHITE = 1

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
ARC_WIDTH      = 19          # set 20 if you want a hair thicker arc
ARC_R_IN       = ARC_R_OUT - ARC_WIDTH

# Optional offsets to nudge the arc on screen
ARC_X_OFFSET = 2
ARC_Y_OFFSET = 0

# Angle convention (0..360, Y-down):
# right=0°, down=90°, left=180°, up=270°.
ARC_LEFT_DEG = 180.0
ARC_UP_DEG   = 270.0         # max sweep (strict 90°)

class MotorPowerWidget:
    def __init__(self, fb, display_width, display_height):
        self.fb = fb
        self.dw = display_width
        self.dh = display_height
        self._prev_rect_w = -1
        self._prev_A_end  = None
        self._has_hline = hasattr(self.fb, "hline")

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

    def _rect(self, x, y, w, h, c=WHITE, fill=False):
        if fill:
            self.fb.fill_rect(int(x), int(y), int(w), int(h), c)
        else:
            self.fb.rect(int(x), int(y), int(w), int(h), c)

    def _draw_bucket_outline(self):
        # Top bar outline (WHITE)
        s_y = 0
        w   = 62
        w2  = w // 2
        self._line(w2 + 5, s_y + 18, w, s_y + 18, WHITE)
        self._line(w2 + 5, s_y +  0, w, s_y +  0, WHITE)
        self._line(w,      s_y +  0, w, s_y + 18, WHITE)

    def _draw_arc_outlines(self):
        # crisp inner & outer outlines for the 90° sector (sample per degree)
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET
        def poly_arc(r):
            prev = None
            for a in range(int(ARC_LEFT_DEG), int(ARC_UP_DEG) + 1):
                rad = math.radians(a)
                x = int(cx + r * math.cos(rad))
                y = int(cy + r * math.sin(rad))  # Y-down
                if prev:
                    self._line(prev[0], prev[1], x, y, WHITE)
                prev = (x, y)
        poly_arc(ARC_R_IN)
        poly_arc(ARC_R_OUT)

    # -------- Analytic scanline span for a given angle A --------
    def _fill_wedge_scanlines(self, A_end_deg, color):
        """
        Draw the ring sector angles in [180°, A_end] using horizontal spans.
        """
        cx = ARC_CX + ARC_X_OFFSET
        cy = ARC_CY + ARC_Y_OFFSET

        # Clamp angle
        A = float(A_end_deg)
        if A < ARC_LEFT_DEG:  A = ARC_LEFT_DEG
        if A > ARC_UP_DEG:    A = ARC_UP_DEG
        Arad = math.radians(A)

        r_out2 = ARC_R_OUT * ARC_R_OUT
        r_in2  = ARC_R_IN  * ARC_R_IN

        tanA = math.tan(Arad)
        tiny = 1e-6

        # Only rows in the upper half (y <= cy)
        y_min = cy - ARC_R_OUT
        y_max = cy

        for y in range(y_min, y_max + 1):
            dy = y - cy
            dy2 = dy * dy
            if dy2 > r_out2:
                continue

            # Outer circle left intersection
            x_out = math.sqrt(r_out2 - dy2)
            x_left = int(math.floor(cx - x_out))

            # Inner circle left boundary (if exists)
            if dy2 <= r_in2:
                x_in = math.sqrt(r_in2 - dy2)
                x_inner_edge = cx - x_in
            else:
                x_inner_edge = float('inf')  # no inner limit this row

            # Angle boundary
            if abs(tanA) > tiny:
                dx_ang = dy / tanA      # dx negative for our sector
                x_angle_edge = cx + dx_ang
            else:
                x_angle_edge = -1e9     # A~180°, include full left annulus

            x_right_f = min(x_inner_edge, x_angle_edge)
            x_right = int(math.floor(x_right_f))

            if x_right >= x_left:
                self._hline(x_left, y, x_right - x_left + 1, color)

    # ---- public API ----
    def draw_contour(self):
        # Called once at boot
        self._draw_bucket_outline()
        self._draw_arc_outlines()
        # Force rect state so first update will repaint the bar area
        self._prev_rect_w = -9999   # force first update to clear + draw

    def update(self, motor_power_percent):
        p = int(max(0, min(100, motor_power_percent)))

        # ---- ring fill (0..50%) ----
        p_arc = min(p, 50)
        if p_arc == 0:
            A_end = ARC_LEFT_DEG
        else:
            t = p_arc / 50.0
            A_end = ARC_LEFT_DEG + 90.0 * t  # 180 → 270

        # Minimal clear: erase old wedge only (draw it in BLACK),
        # then draw the new wedge in WHITE.
        if self._prev_A_end is not None and A_end != self._prev_A_end:
            self._fill_wedge_scanlines(self._prev_A_end, BLACK)

        if self._prev_A_end is None or A_end != self._prev_A_end:
            if p_arc > 0:
                self._fill_wedge_scanlines(A_end, WHITE)
            self._draw_arc_outlines()   # keep ring edges crisp
            self._prev_A_end = A_end

        # ---- top bar (50..100%) ----
        rect_w = 0
        if p > 50:
            rect_w = int(map_value(p, 50, 100, 0, motor_power_width))

        if rect_w != self._prev_rect_w:
            # Clear only the inside of the bucket (not the outline)
            self._rect(motor_power_x + motor_power_width + 9,
                       motor_power_y, motor_power_width, motor_power_height + 1,
                       BLACK, fill=True)
            if rect_w > 0:
                self._rect(motor_power_x + motor_power_width + 9,
                           motor_power_y, rect_w, motor_power_height + 1,
                           WHITE, fill=True)
            self._draw_bucket_outline()
            self._prev_rect_w = rect_w
            
        self._draw_bucket_outline()
