# display_st7565_mpy.py
# MicroPython ST7565/ST7567 driver aligned to the CircuitPython init you confirmed working.
# - Page addressing, MONO_VLSB framebuffer
# - Column offset (colstart) support (many ST7567 boards need 4)
# - Bias / contrast / ADC / COM scan / start line controls

import time
import framebuf
from machine import Pin, SPI, PWM

# --- Bias commands (per datasheet) ---
BIAS_7 = 0xA3  # 1/7
BIAS_9 = 0xA2  # 1/9

class ST7565(framebuf.FrameBuffer):
    def __init__(
        self,
        spi,
        cs: Pin,
        dc: Pin,
        rst: Pin,
        *,
        width=128,
        height=64,
        colstart=4,            # CP driver uses colstart=4 for your board
        resistor_ratio=0x20,   # CP snippet sets 0x20
        initial_contrast=0,    # CP snippet sets contrast to 0 after init
        use_adc_reverse=True,  # CP uses A1
        use_com_normal=True,   # CP uses C0
        use_bias_1_7=True,     # CP uses A3
    ):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = int(width)
        self.height = int(height)

        # Pins
        self.cs.init(Pin.OUT, value=1)
        self.dc.init(Pin.OUT, value=0)
        self.rst.init(Pin.OUT, value=1)

        # Framebuffer (pages of 8 rows)
        self.pages = self.height // 8
        self.buf = bytearray(self.width * self.pages)
        super().__init__(self.buf, self.width, self.height, framebuf.MONO_VLSB)

        # State (mirrors CP defaults)
        self._contrast = max(0, min(int(initial_contrast), 63))
        self._bias = BIAS_7 if use_bias_1_7 else BIAS_9
        self._reverse = False
        self._colstart = colstart & 0x7F
        self._res_ratio = 0x20 if (resistor_ratio < 0x20 or resistor_ratio > 0x27) else resistor_ratio
        self._start_line = 0
        self._adc_reverse = bool(use_adc_reverse)   # A1
        self._com_normal  = bool(use_com_normal)    # C0

        # Init HW matching the CP sequence you posted
        self._hw_init()

    # ---------- low-level ----------
    def reset(self):
        self.rst(0); time.sleep_ms(20)
        self.rst(1); time.sleep_ms(20)

    def cmd(self, c):
        self.cs(0); self.dc(0)
        self.spi.write(bytearray([c & 0xFF]))
        self.cs(1)

    def data(self, b):
        self.cs(0); self.dc(1)
        self.spi.write(b)
        self.cs(1)

    def _hw_init(self):
        self.reset()
        self.cmd(0xAE)                                   # display OFF
        self.cmd(self._bias)                             # A3 (1/7) or A2 (1/9)
        self.cmd(0xA1 if self._adc_reverse else 0xA0)    # ADC select: A1 matches CP
        self.cmd(0xC0 if self._com_normal else 0xC8)     # COM scan:  C0 matches CP
        self.cmd(0x40 | (self._start_line & 0x3F))       # start line

        # Power-up sequence (CP adds length bytes; we do delays)
        self.cmd(0x2C); time.sleep_ms(50)                # VC on
        self.cmd(0x2E); time.sleep_ms(50)                # VR on
        self.cmd(0x2F); time.sleep_ms(10)                # VF on

        # Operating voltage (regulator resistor ratio)
        self.cmd(self._res_ratio)                        # 0x20..0x27; CP uses 0x20

        self.cmd(0xAF)                                   # display ON
        self.cmd(0xA4)                                   # follow RAM (not all points on)

        # Initial contrast (CP sends 0 after 0x81)
        self._write_contrast(self._contrast)

    # ---------- public controls ----------
    @property
    def reverse(self):
        return self._reverse

    @reverse.setter
    def reverse(self, state: bool):
        self._reverse = bool(state)
        self.cmd(0xA7 if self._reverse else 0xA6)  # invert display

    @property
    def contrast(self) -> int:
        return self._contrast

    @contrast.setter
    def contrast(self, value: int):
        self._contrast = max(0, min(int(value), 63))
        self._write_contrast(self._contrast)

    def _write_contrast(self, level: int):
        self.cmd(0x81)                 # electronic volume set
        self.cmd(level & 0x3F)         # 0..63

    @property
    def bias(self) -> int:
        return self._bias

    @bias.setter
    def bias(self, bias_cmd: int):
        if bias_cmd not in (BIAS_7, BIAS_9):
            raise ValueError("bias must be BIAS_7 or BIAS_9")
        self._bias = bias_cmd
        self.cmd(self._bias)

    def set_adc(self, reverse: bool):
        self._adc_reverse = bool(reverse)
        self.cmd(0xA1 if self._adc_reverse else 0xA0)

    def set_com_scan(self, normal: bool):
        self._com_normal = bool(normal)
        self.cmd(0xC0 if self._com_normal else 0xC8)

    def set_resistor_ratio(self, rr: int):
        rr = 0x20 if (rr < 0x20 or rr > 0x27) else rr
        self._res_ratio = rr
        self.cmd(self._res_ratio)

    def set_start_line(self, line: int):
        self._start_line = line & 0x3F
        self.cmd(0x40 | self._start_line)

    def set_colstart(self, colstart: int):
        self._colstart = colstart & 0x7F

    def set_orientation(self, *, adc_reverse=None, com_reverse=None):
        """
        Optional helper to flip X/Y if you need it later.
        CP 'working' init is adc_reverse=True, com_reverse=False.
        """
        if adc_reverse is not None:
            self.set_adc(bool(adc_reverse))
        if com_reverse is not None:
            # com_reverse=True -> use C8, i.e., normal=False
            self.set_com_scan(not bool(com_reverse))

    def show(self):
        """
        Flush the framebuffer to the LCD applying the column offset (colstart).
        """
        off = self._colstart & 0x7F
        hi = 0x10 | ((off >> 4) & 0x0F)
        lo = 0x00 | (off & 0x0F)
        for page in range(self.pages):
            self.cmd(0xB0 | page)  # page address
            self.cmd(hi)           # high column (with offset)
            self.cmd(lo)           # low column  (with offset)
            start = page * self.width
            end = start + self.width
            self.data(self.buf[start:end])


# -------- Wrapper with PWM backlight (same public API you used) -------------
class Display:
    def __init__(
        self,
        spi_clk_pin,
        spi_mosi_pin,
        chip_select_pin,
        command_pin,
        reset_pin,
        backlight_pin,
        spi_clock_frequency,
        *,
        spi_id=1,            # SPI(1) is common on ESP32
        colstart=4,          # CP working config for your board
        resistor_ratio=0x20,
        initial_contrast=0,
        use_adc_reverse=True,   # A1
        use_com_normal=True,    # C0
        use_bias_1_7=True,      # A3
        backlight_inverted=True,  # many boards: 0=ON
    ):
        # SPI (MISO not needed)
        self.spi = SPI(
            spi_id,
            baudrate=spi_clock_frequency,
            polarity=0,
            phase=0,
            sck=Pin(spi_clk_pin),
            mosi=Pin(spi_mosi_pin),
            miso=None,
        )

        cs  = Pin(chip_select_pin, Pin.OUT, value=1)
        dc  = Pin(command_pin,     Pin.OUT, value=0)
        rst = Pin(reset_pin,       Pin.OUT, value=1)

        self._display = ST7565(
            self.spi, cs, dc, rst,
            width=128, height=64,
            colstart=colstart,
            resistor_ratio=resistor_ratio,
            initial_contrast=initial_contrast,
            use_adc_reverse=use_adc_reverse,
            use_com_normal=use_com_normal,
            use_bias_1_7=use_bias_1_7,
        )

        # Backlight PWM (kHz). Invert if your board uses 0=ON.
        self._bl_inverted = bool(backlight_inverted)
        self._backlight = PWM(Pin(backlight_pin), freq=10_000)
        self.backlight_pwm(0.5)

        # Defaults: no extra flips here, stays as A1/C0 like CP working 
        self._display.contrast = initial_contrast  # start at 0; adjust later as needed
        
        self._display.set_orientation(adc_reverse=False, com_reverse=True)

    @property
    def display(self) -> ST7565:
        return self._display  # FrameBuffer with .show()

    def backlight_pwm(self, duty_cycle_percent=0.5):
        """
        Set backlight brightness (0.0..1.0). If inverted, 0.0 = full ON.
        """
        p = max(0.0, min(float(duty_cycle_percent), 1.0))
        val = int(65535 * p)
        if self._bl_inverted:
            self._backlight.duty_u16(65535 - val)
        else:
            self._backlight.duty_u16(val)
            
    @property
    def framebuf(self):
        # expose the internal FrameBuffer
        return self._display

    def show(self):
        # flush to LCD
        self._display.show()
