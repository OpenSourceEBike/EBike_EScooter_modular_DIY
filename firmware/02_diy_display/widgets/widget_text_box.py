# widget_text_box.py  — Low-RAM version (glyph-by-glyph into the box)
import framebuf
from lcd.writer import Writer

# FB that "reports" big dims so Writer accepts fonts if we ever need it
class _FBWithWH(framebuf.FrameBuffer):
    def __init__(self, buf, w, h, fmt, reported_w=None, reported_h=None):
        super().__init__(buf, w, h, fmt)
        self.width  = reported_w if reported_w is not None else w
        self.height = reported_h if reported_h is not None else h

class WidgetTextBox:
    """
    Hard-clipped text in a box (RAM-friendly).
      - set_box(x1,y1,x2,y2) sets the clipping rectangle (inclusive).
      - OR anchor/pattern mode if you skip set_box.
      - set_text_pos(x,y) pins the TEXT (natural top-left) at absolute screen coords.
        (When set_text_pos is used, align_inside is ignored.)
      - Trims (left/right/top/bottom) shave pixels from the text bbox.
      - align_inside: 'left' | 'center' | 'right' (used only when set_text_pos is not set).
      - Debug outline optional.

    Low-RAM: renders per-glyph straight into the box buffer, no full-text buffer.
    """

    def __init__(self, fb, disp_w, disp_h, *, font,
                 box=None, x=None, y=None, anchor="topright", pattern=None,
                 fg=1, bg=0,
                 left=0, right=0, top=0, bottom=0,
                 align_inside="right",
                 content_dx=0, content_dy=0,
                 debug_box=False, formatter=None):
        self.fb = fb
        self.disp_w = disp_w
        self.disp_h = disp_h
        self.font = font
        self.fg = fg
        self.bg = bg

        self._box_coords = box
        self.anchor = anchor if anchor in ("topleft","topright") else "topleft"
        self.x = 0 if x is None else int(x)
        self.y = 0 if y is None else int(y)
        self.pattern = pattern

        # accept 'center'
        self.align_inside = "right" if align_inside not in ("left","center","right") else align_inside

        self.left = int(left); self.right = int(right)
        self.top  = int(top);  self.bottom = int(bottom)
        self.content_dx = int(content_dx); self.content_dy = int(content_dy)
        self.debug_box = bool(debug_box)
        self.formatter = formatter

        # visibility + last content
        self.visible = True
        self._last_text = None     # resolved string (after formatter)
        self._last_valid = False

        self._text_pos = None         # absolute TEXT position (screen coords)
        self._text_pos_anchor = "topleft"

        # Learn framebuf format from a Writer on the real framebuffer
        wr = Writer(self.fb, self.font, verbose=False)
        wr.set_clip(row_clip=True, col_clip=True, wrap=False)
        wr.set_vclip(True)
        self._map = wr.map

        self._prev_box = None

    # ---------- visibility API ----------
    def set_visible(self, visible: bool, clear: bool = True):
        """
        Toggle widget visibility.
        - When turning OFF and clear=True, clears the previously drawn box.
        - When turning ON, redraws using the last valid text (if any).
        """
        visible = bool(visible)
        if visible == self.visible:
            return

        if not visible:
            # Going hidden
            if clear and self._prev_box:
                self._clear(self._prev_box)
                if self.debug_box:
                    self._box_outline(self._prev_box)
            self.visible = False
            # We keep _prev_box so a later show() can reuse placement if needed
        else:
            # Going visible
            self.visible = True
            if self._last_valid and self._last_text is not None:
                # Force a redraw with the last content
                self.update(self._last_text, valid=True)

    def hide(self, clear: bool = True):
        self.set_visible(False, clear=clear)

    def show(self):
        self.set_visible(True, clear=False)

    def is_visible(self) -> bool:
        return self.visible

    # ---------- helpers ----------
    def _as_text(self, obj):
        if isinstance(obj, str):
            return obj
        if self.formatter:
            try:
                return self.formatter.format(obj)
            except:
                pass
        return str(obj)

    def _text_size(self, s):
        if not s:
            return 0, self.font.height()
        w = 0
        for ch in s:
            _, _, cw = self.font.get_ch(ch)
            w += cw
        return w, self.font.height()

    def _box_from_coords(self, x1, y1, x2, y2):
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1
        w = (x2 - x1) + 1
        h = (y2 - y1) + 1
        if x1 < 0:  w += x1; x1 = 0
        if y1 < 0:  h += y1; y1 = 0
        if x1 + w > self.disp_w:  w = self.disp_w - x1
        if y1 + h > self.disp_h:  h = self.disp_h - y1
        if w < 1 or h < 1: return 0,0,0,0
        return x1, y1, w, h

    def _compute_box_from_pattern(self, base_string):
        tw, th = self._text_size(base_string)
        L = max(0, self.left); R = max(0, self.right)
        T = max(0, self.top);  B = max(0, self.bottom)
        bw = max(1, tw - (L + R))
        bh = max(1, th - (T + B))
        bx = self.x if self.anchor == "topleft" else (self.x - bw + 1)
        by = self.y
        if bx < 0: bw += bx; bx = 0
        if by < 0: bh += by; by = 0
        if bx + bw > self.disp_w: bw = self.disp_w - bx
        if by + bh > self.disp_h: bh = self.disp_h - by
        if bw < 1 or bh < 1: return 0,0,0,0
        return bx, by, bw, bh

    def _clear(self, rect):
        x,y,w,h = rect
        if w and h:
            self.fb.fill_rect(x, y, w, h, self.bg)

    def _box_outline(self, rect):
        x,y,w,h = rect
        if w and h:
            self.fb.rect(x, y, w, h, self.fg)

    # ---------- public ----------
    def set_box(self, x1, y1, x2, y2):
        self._box_coords = (int(x1), int(y1), int(x2), int(y2))

    def set_box_wh(self, x, y, w, h):
        self._box_coords = (int(x), int(y), int(x)+int(w)-1, int(y)+int(h)-1)

    def set_trims(self, *, left=None, right=None, top=None, bottom=None):
        if left   is not None: self.left   = int(left)
        if right  is not None: self.right  = int(right)
        if top    is not None: self.top    = int(top)
        if bottom is not None: self.bottom = int(bottom)

    def set_content_offset(self, dx=None, dy=None):
        if dx is not None: self.content_dx = int(dx)
        if dy is not None: self.content_dy = int(dy)

    def set_pattern(self, pattern=None):
        self.pattern = pattern

    def set_text_pos(self, x, y):
        self._text_pos = (int(x), int(y))
        self._text_pos_anchor = "topleft"

    def clear_text_pos(self):
        self._text_pos = None

    def invalidate(self):
        if self._prev_box:
            self._clear(self._prev_box)
            if self.debug_box:
                self._box_outline(self._prev_box)
            self._prev_box = None

    # ---------- drawing (LOW RAM) ----------
    def update(self, text, valid=True):
        # Store last content so show() can redraw immediately
        if not valid or text is None:
            self._last_text = None
            self._last_valid = False
            if self.visible:
                self.invalidate()
            return
        s = self._as_text(text)
        self._last_text = s
        self._last_valid = True

        if not self.visible:
            # Don't draw while hidden (keeps RAM usage minimal)
            return

        # 1) Box (visible clip)
        if self._box_coords:
            bx, by, bw, bh = self._box_from_coords(*self._box_coords)
        else:
            base = self.pattern if self.pattern is not None else s
            bx, by, bw, bh = self._compute_box_from_pattern(base)
        if bw == 0 or bh == 0:
            return

        # 2) Clear old/current visible regions
        if self._prev_box:
            self._clear(self._prev_box)
        self._clear((bx, by, bw, bh))

        # 3) Make the CLIP buffer (only buffer we allocate)
        bytes_row_clip = (bw + 7) // 8
        buf_clip = bytearray(bytes_row_clip * bh)
        # Report bigger dims so we could use Writer on it if needed (not required here)
        clipfb = _FBWithWH(buf_clip, bw, bh, self._map, self.font.max_width()+1, self.font.height()+1)
        clipfb.fill(self.bg)

        # 4) Compute base placement of the *text top-left* inside the clip buffer
        L = max(0, self.left); R = max(0, self.right); T = max(0, self.top)

        # Measure text width/height
        tw, th = self._text_size(s)

        if self._text_pos is not None:
            # Absolute text position in SCREEN coords
            tx_abs, ty_abs = self._text_pos
            dest_x = (tx_abs - bx) - L
            dest_y = (ty_abs - by) - T
        else:
            # Align inside the box
            if self.align_inside == "right":
                dest_x = bw - (tw - R) - L
            elif self.align_inside == "center":
                # center the *visible* portion (after trims L/R) inside bw
                visible_tw = max(0, tw - (L + R))
                dest_x = (bw - visible_tw) // 2 - L
            else:  # 'left'
                dest_x = -L
            dest_y = -T

        # Apply user nudge
        dest_x += self.content_dx
        dest_y += self.content_dy

        # 5) Render GLYPH-BY-GLYPH into the clip buffer (low RAM)
        advance_x = 0
        for ch in s:
            glyph, gh, gw = self.font.get_ch(ch)
            # skip empty glyphs safely
            if gw <= 0 or gh <= 0 or glyph is None:
                continue

            # Destination for this glyph inside the clip buffer
            gx = dest_x + advance_x
            gy = dest_y

            # Quick reject if the glyph is completely outside the clip buffer
            if gx >= bw or gy >= bh or gx + gw <= 0 or gy + gh <= 0:
                advance_x += gw
                continue

            # Prepare a FrameBuffer over the glyph bitmap (mono)
            # (bytearray() makes a mutable copy; cost ~ceil(gw/8)*gh bytes per glyph)
            try:
                gbuf = bytearray(glyph)
            except MemoryError:
                # if we still hit RAM limits, skip this glyph gracefully
                advance_x += gw
                continue
            gf = framebuf.FrameBuffer(gbuf, gw, gh, self._map)

            # Blit glyph into the clip buffer; negative gx/gy are fine (it clips)
            clipfb.blit(gf, gx, gy)

            advance_x += gw  # move to next glyph position

        # 6) Blit the clipped buffer to the screen
        self.fb.blit(clipfb, bx, by)
        if self.debug_box:
            self._box_outline((bx, by, bw, bh))
        self._prev_box = (bx, by, bw, bh)
