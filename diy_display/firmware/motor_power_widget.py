# motor_power_widget_mpy.py
# MicroPython version using framebuf (RGB565). No displayio/vectorio needed.

import math
import framebuf

# Colors (RGB565)
BLACK = 0x0000
WHITE = 0xFFFF

def map_value(x, in_min, in_max, out_min, out_max):
    x = max(min(x, in_max), in_min)
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

class MotorPowerWidget:
    """
    Draws a semi-circular arc (0–50%) and a horizontal bar (50–100%).
    Requires an object with a framebuf-like API:
      - pixel(x,y,color), line(x0,y0,x1,y1,color),
        rect(x,y,w,h,color), fill_rect(x,y,w,h,color)
    """
    def __init__(self, fb: framebuf.FrameBuffer, display_width, display_height):
        self.fb = fb
        self._d_width = display_width
        self._d_height = display_height
        self._angle_previous = -999

        # Layout (match your original geometry as close as possible)
        self.cx = 36
        self.cy = 36
        self.outer_r = 37
        self.inner_r = 37 - 19  # because arc_width=19 in original
        self.arc_thickness = 19

        # Rectangle (power > 50%)
        self.motor_power_width = 26
        self.motor_power_height = 18
        self.motor_power_x = 2
        self.motor_power_y = 0

        # Right-side frame box (contour)
        self.box_w = 62
        self.box_h = 35
        self.box_sx = 0
        self.box_sy = 0

        # Pre-clear area we draw into (optional)
        self.clear_color = BLACK
        self.fg = WHITE

    # --------- low-level helpers ----------
    def _draw_thick_point(self, x, y, thickness, color):
        # Small square for thickness (simple & fast)
        r = thickness // 2
        self.fb.fill_rect(x - r, y - r, thickness, thickness, color)

    def _draw_arc(self, cx, cy, r_outer, thickness, deg_start, deg_end, color, step_deg=4):
        """Approximate a thick arc by plotting small squares along its outer edge
        and filling inward (simple + decent performance)."""
        r_inner = max(0, r_outer - thickness + 1)
        for a in range(int(deg_start), int(deg_end) + 1, step_deg):
            rad = math.radians(a)
            x_o = int(cx + r_outer * math.cos(rad))
            y_o = int(cy - r_outer * math.sin(rad))
            x_i = int(cx + r_inner * math.cos(rad))
            y_i = int(cy - r_inner * math.sin(rad))
            # Draw a short radial line to simulate thickness
            self._line(x_i, y_i, x_o, y_o, color)

    def _line(self, x0, y0, x1, y1, color):
        # Use framebuf.line if present, else Bresenham
        try:
            self.fb.line(x0, y0, x1, y1, color)
        except AttributeError:
            self._bresenham(x0, y0, x1, y1, color)

    def _bresenham(self, x0, y0, x1, y1, color):
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

    # ---------- public API ----------
    def draw_contour(self):
        # Clear region we use (optional; comment out if you manage screen elsewhere)
        # self.fb.fill_rect(0, 0, self._d_width, self._d_height, self.clear_color)

        # Two thin arcs (like your outline arcs)
        # Original had: arc_1 angle=-90 to 90+45; arc_2 similar with smaller radius
        # We'll draw outer thin arc (width=2) and inner thin arc (width=2).
        self._draw_arc(self.cx, self.cy, self.outer_r, 2, -90, 135, self.fg, step_deg=3)
        self._draw_arc(self.cx, self.cy, 19,        2, -90, 135, self.fg, step_deg=3)

        # Horizontal line from (0,36) to (19,36)
        self._line(0, 36, 19, 36, self.fg)

        # Right-side rectangle “frame” like l2/l3/l4
        w2_plus5 = (self.box_w // 2) + 5
        # top and bottom lines
        self._line(w2_plus5, self.box_sy,   self.box_w, self.box_sy,   self.fg)
        self._line(w2_plus5, self.box_sy+18, self.box_w, self.box_sy+18, self.fg)
        # right vertical
        self._line(self.box_w, self.box_sy, self.box_w, self.box_sy+18, self.fg)

    def update(self, motor_power_percent):
        # Clamp
        p = 0 if motor_power_percent < 0 else 100 if motor_power_percent > 100 else motor_power_percent

        # ----- Arc (0..50%) -----
        # Map 0..50% -> 0..90 degrees, drawn over the big arc span.
        angle = int(map_value(p, 0, 50, 0, 90))
        if angle != self._angle_previous:
            # Clear arc area first (simple way: redraw a BLACK thick arc over full span)
            # Big span is [-90 .. 135]; we only use [-90 .. (-90 + angle)]
            # To avoid ghosts, wipe the whole arc sector then draw the new filling.
            self._draw_arc(self.cx, self.cy, self.outer_r, self.arc_thickness, -90, 135, BLACK, step_deg=2)
            if angle > 0:
                self._draw_arc(self.cx, self.cy, self.outer_r, self.arc_thickness,
                               -90, -90 + angle, self.fg, step_deg=2)
            self._angle_previous = angle

        # ----- Rectangle bar (50..100%) -----
        # Erase the full bar region first
        self.fb.fill_rect(self.motor_power_x + self.motor_power_width + 9,
                          self.motor_power_y,
                          self.motor_power_width,
                          self.motor_power_height + 1,
                          BLACK)

        if p > 50:
            width_power = int(map_value(p, 50, 100, 0, self.motor_power_width))
            if width_power > 0:
                self.fb.fill_rect(self.motor_power_x + self.motor_power_width + 9,
                                  self.motor_power_y,
                                  width_power,
                                  self.motor_power_height + 1,
                                  WHITE)
