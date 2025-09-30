# widget_clock.py
import framebuf
from writer import Writer

class WidgetClock:
    """
    Relógio hh:mm alinhado ao canto inferior-direito (vidro).
    - Limpa apenas uma caixa fixa (dimensionada para "88:88").
    - Evita redraw se o texto não mudou.
    - Permite apagar quando tempo inválido.
    - Controlos de posicionamento:
        * x_offset / y_offset movem a CAIXA.
        * baseline_adjust ajusta a linha de base (↑ negativo, ↓ positivo).
        * top_nudge ajusta o TEXTO dentro da caixa (↓ positivo).
    - Ativa vclip no Writer para permitir encostar ao vidro (cortar linhas de baixo).
    """

    def __init__(
        self,
        fb: framebuf.FrameBuffer,
        display_width: int,
        display_height: int,
        *,
        font,
        fg=1,
        bg=0,
        x_offset: int = 0,
        y_offset: int = 0,
        baseline_adjust: int = 0,
        top_nudge: int = 0,
    ):
        self.fb = fb
        self._w = display_width
        self._h = display_height
        self.font = font
        self.fg = fg
        self.bg = bg

        # Writer sem fg/bg (monocromático) + vclip ON
        self._writer = Writer(self.fb, self.font, verbose=False)
        self._writer.set_clip(row_clip=True, col_clip=True, wrap=False)
        self._writer.set_vclip(True)  # permite encostar ao vidro

        # Âncora no vidro (canto inferior-direito)
        self.anchor_x = self._w - 1
        self.anchor_y = self._h - 1

        # Tamanho máximo para limpeza
        self._max_w = self._text_width("88:88")
        self._max_h = self.font.height()

        # Ajustes
        self._x_offset = x_offset
        self._y_offset = y_offset
        self._baseline_adjust = baseline_adjust
        self._top_nudge = top_nudge

        # Caixa fixa de limpeza
        self._recalc_box()

        self._last_txt = None

    # ---------- helpers ----------
    def _recalc_box(self):
        self._box_x = max(0, self.anchor_x - self._max_w + 1 + self._x_offset)
        self._box_y = max(
            0,
            self.anchor_y - self._max_h + 1 + self._baseline_adjust + self._y_offset
        )
        self._box_w = self._max_w
        self._box_h = self._max_h

    def _text_width(self, s: str) -> int:
        w = 0
        for ch in s:
            _, _, cw = self.font.get_ch(ch)
            w += cw
        return w

    def _clear_box(self):
        self.fb.fill_rect(self._box_x, self._box_y, self._box_w, self._box_h, self.bg)

    # ---------- public ----------
    def set_offsets(self, *, x_offset: int = None, y_offset: int = None,
                    baseline_adjust: int = None, top_nudge: int = None):
        if x_offset is not None:
            self._x_offset = x_offset
        if y_offset is not None:
            self._y_offset = y_offset
        if baseline_adjust is not None:
            self._baseline_adjust = baseline_adjust
        if top_nudge is not None:
            self._top_nudge = top_nudge
        self._recalc_box()

    def invalidate(self):
        self._clear_box()
        self._last_txt = None

    def update(self, hour: int = None, minute: int = None, valid: bool = True):
        if not valid or hour is None or minute is None:
            self.invalidate()
            return

        txt = f"{hour:02}:{minute:02}"

        if txt == self._last_txt:
            return

        self._clear_box()

        w_txt = self._text_width(txt)
        x_txt = self.anchor_x - w_txt + 1 + self._x_offset
        if x_txt < 0:
            x_txt = 0

        y_txt = self._box_y + self._top_nudge

        Writer.set_textpos(self.fb, y_txt, x_txt)
        self._writer.printstring(txt)
        self._last_txt = txt

    def update_from_tuple(self, dt_tuple, valid: bool = True):
        if not valid or not dt_tuple or len(dt_tuple) < 5:
            self.invalidate()
            return
        h, m = dt_tuple[3], dt_tuple[4]
        if (h is None) or (m is None) or not (0 <= h <= 23) or not (0 <= m <= 59):
            self.invalidate()
            return
        self.update(h, m, valid=True)
