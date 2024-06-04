# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2024 Mateusz Nowak
#
# SPDX-License-Identifier: MIT

"""
`displayio_st7565`
================================================================================

CircuitPython displayio library for ST7565 and ST7567 controllers, based on the
original framebuf implementation.

As a community effort, this library was tested with only one ST7567 display and
may be not fully compatible with other hardware.

* Author(s): Mateusz Nowak

Implementation Notes
--------------------

**Hardware:**

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads
"""

# Support both 8.x.x and 9.x.x. Change when 8.x.x is discontinued as a stable release.
try:
    from fourwire import FourWire
    from busdisplay import BusDisplay
except ImportError:
    from displayio import FourWire
    from displayio import Display as BusDisplay

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/mateusznowakdev/CircuitPython_DisplayIO_ST7565.git"


_INIT_SEQUENCE = (
    b"\xA3\x00"  # LCD bias select (default 1/7)
    b"\xA1\x00"  # ADC select
    b"\xC0\x00"  # SHL select
    b"\x40\x00"  # Initial display line
    b"\x2C\x80\x32"  # Turn on voltage converter (VC=1, VR=0, VF=0)
    b"\x2E\x80\x32"  # Turn on voltage regulator (VC=1, VR=1, VF=0)
    b"\x2F\x80\x0A"  # Turn on voltage follower (VC=1, VR=1, VF=1)
    # b"\x27\x00"  # Set lcd operating voltage (regulator resistor, ref voltage resistor)
    b"\x20\x00"  # Set lcd operating voltage (regulator resistor, ref voltage resistor)
    b"\xAF\x00"  # Turn on display
    b"\xA4\x00"  # Display all points
    b"\x81\x00\x00"  # Set initial contrast
)

#: Bias value of 1/7
BIAS_7 = 0xA3

#: Bias value of 1/9
BIAS_9 = 0xA2


class ST7565(BusDisplay):
    """ST7565 and ST7567 display driver"""

    def __init__(self, bus: FourWire, **kwargs) -> None:
        init_sequence = bytearray(_INIT_SEQUENCE)
        super().__init__(
            bus,
            init_sequence,
            **kwargs,
            data_as_commands=True,
            SH1107_addressing=True,
            color_depth=1,
            grayscale=True,
            single_byte_bounds=True,
            pixels_in_byte_share_row=False,
            colstart=4 # needed for ST7567: "OPEN-SMART Breakout Board Module para Arduino, LCD Shield, Backlight, LED, 3.3V, 1.8 ", 128x64, Serial SPI, Monocromático"
        )

        self._bias = 0
        self._contrast = 0

    @property
    def bias(self) -> int:
        """
        LCD bias value represents voltage applied to the display.

        This value can be changed if the displayed image is dark and unreadable even at the minimal
        contrast setting.
        """
        return self._bias

    @bias.setter
    def bias(self, bias: int) -> None:
        if bias not in (BIAS_7, BIAS_9):
            raise ValueError(
                "bias setting must be either displayio_st7565.BIAS_7 or displayio_st7565.BIAS_9"
            )

        self._bias = bias
        self.bus.send(self._bias, bytearray())

    @property
    def contrast(self) -> int:
        """LCD contrast value, or "electronic volume" according to the datasheet."""

        return self._contrast

    @contrast.setter
    def contrast(self, contrast: int) -> None:
        if not 0 <= contrast <= 0b00111111:
            raise ValueError("contrast value must be in range 0-63")

        self._contrast = contrast
        self.bus.send(0x81, bytearray())  # Electronic volume set
        self.bus.send(self._contrast, bytearray())

    @contrast.setter
    def reverse(self, state: bool) -> None:
        if state is 0xA7 or 0xA6:
            value = 0xA7 if state else 0xA6
            self.bus.send(value, bytearray())