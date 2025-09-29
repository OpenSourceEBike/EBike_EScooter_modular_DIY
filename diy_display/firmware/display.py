# display_st7565_mpy.py
# MicroPython ST7565/ST7567 driver with init aligned to the CircuitPython reference.
# - Page addressing, MONO_VLSB framebuffer
# - Column offset (colstart) support
# - Tunable bias / contrast / ADC / COM scan / start line
#
# Tested on ESP32/ESP32-C3. Adjust SPI bus and pins in your wrapper.

import time
import framebuf
from machine import Pin, SPI, PWM

# Bias constants (match the CP lib)
BIAS_7 = 0xA3  # 1/7
BIAS_9 = 0xA2  # 1/9

class ST7565(framebuf.FrameBuffer):
    def __init__(self, spi, cs, dc, rst,
                 width=128, height=64,
                 colstart=4,         # many ST7567 boards need 4
                 resistor_ratio=0x20, # CP ref uses 0x20 (0x20..0x27 valid)
                 initial_contrast=0, # CP ref sets 0 after power-up, then you can change
                 use_adc_reverse=True,  # CP ref: A1
                 use_com_normal=True,   # CP ref: C0
                 use_bias_1_7=True,     # CP ref: A3
                 ):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height

        # pins
        self.cs.init(Pin.OUT, value=1)
        self.dc.init(Pin.OUT, value=0)
        self.rst.init(Pin.OUT, value=1)

        # buffer (pages of 8 rows)
        self.pages = height // 8
        self.buf = bytearray(self.width * self.pages)
        super().__init__(self.buf, self.width, self.height, framebuf.MONO_VLSB)

        # state
        self._contrast = max(0, min(int(initial_contrast), 63))
        self._bias = BIAS_7 if use_bias_1_7 else BIAS_9
        self._reverse = False
        self._colstart = colstart & 0x7F
        self._res_ratio = resistor_ratio & 0x27  # valid range 0x20..0x27
        self._start_line = 0

        # init sequence (mirrors the CircuitPython lib defaults)
        self.reset()
        self.cmd(0xAE)                               # display OFF
        self.cmd(self._bias)                         # bias 1/7 or 1/9
        self.cmd(0xA1 if use_adc_reverse else 0xA0)  # ADC select (A1=reverse)
        self.cmd(0xC0 if use_com_normal else 0xC8)   # COM scan direction (C0=normal)
        self.cmd(0x40 | (self._start_line & 0x3F))   # display start line
        # power-up sequence (converter -> regulator -> follower), with short waits
        self.cmd(0x2C); time.sleep_ms(50)            # VC on
        self.cmd(0x2E); time.sleep_ms(50)            # VR on
        self.cmd(0x2F); time.sleep_ms(10)            # VF on
        # operating voltage (resistor ratios)
        self.cmd(self._res_ratio)                    # 0x20..0x27
        self.cmd(0xAF)                               # display ON
        self.cmd(0xA4)                               # display follows RAM (A5 = all pixels on)
        # initial contrast
        self._write_contrast(self._contrast)

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

    def _write_contrast(self, level):
        # electronic volume set
        self.cmd(0x81)
        self.cmd(level & 0x3F)

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
        self.cmd(0xA1 if reverse else 0xA0)

    def set_com_scan(self, normal: bool):
        self.cmd(0xC0 if normal else 0xC8)

    def set_resistor_ratio(self, rr: int):
        rr &= 0x27
        if rr < 0x20:
            rr = 0x20
        self._res_ratio = rr
        self.cmd(self._res_ratio)

    def set_start_line(self, line: int):
        self._start_line = line & 0x3F
        self.cmd(0x40 | self._start_line)

    def set_colstart(self, colstart: int):
        self._colstart = colstart & 0x7F

    def show(self):
        # Flush the framebuffer to the LCD, respecting page and column offset
        for page in range(self.pages):
            self.cmd(0xB0 | page)  # page address
            # Column address = colstart (high nibble, then low nibble)
            hi = 0x10 | ((self._colstart >> 4) & 0x0F)
            lo = 0x00 | (self._colstart & 0x0F)
            self.cmd(hi)
            self.cmd(lo)
            start = page * self.width
            end = start + self.width
            self.data(self.buf[start:end])


# --- Wrapper with PWM backlight, same public API you were using -------------
class Display(object):
    def __init__(self,
                 spi_clk_pin, spi_mosi_pin,
                 chip_select_pin, command_pin, reset_pin,
                 backlight_pin,
                 spi_clock_frequency,
                 colstart=4):
        # SPI (MISO not needed)
        self.spi = SPI(1,
                       baudrate=spi_clock_frequency,
                       polarity=0, phase=0,
                       sck=Pin(spi_clk_pin),
                       mosi=Pin(spi_mosi_pin),
                       miso=None)

        cs  = Pin(chip_select_pin, Pin.OUT, value=1)
        dc  = Pin(command_pin,     Pin.OUT, value=0)
        rst = Pin(reset_pin,       Pin.OUT, value=1)

        self._display = ST7565(self.spi, cs, dc, rst,
                               width=128, height=64,
                               colstart=colstart,
                               resistor_ratio=0x20,      # match CP ref
                               initial_contrast=0,       # match CP ref
                               use_adc_reverse=True,     # A1
                               use_com_normal=True,      # C0
                               use_bias_1_7=True)        # A3

        # Backlight (invert if your hardware uses 0=ON)
        self._backlight = PWM(Pin(backlight_pin), freq=10_000)
        self.backlight_pwm(0.5)

        # Default look
        self._display.reverse = False
        self._display.contrast = 0  # start at 0, adjust as needed

    @property
    def display(self):
        return self._display  # FrameBuffer with .show()

    def backlight_pwm(self, duty_cycle_percent=0.5, inverted=True):
        p = max(0.0, min(float(duty_cycle_percent), 1.0))
        val = int(65535 * p)
        self._backlight.duty_u16(65535 - val if inverted else val)
