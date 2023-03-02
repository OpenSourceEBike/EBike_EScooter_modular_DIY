import busio
import displayio
import adafruit_displayio_sh1106

class Display(object):
    def __init__(self, spi_clk_pin, spi_mosi_pin, chip_select_pin, command_pin, reset_pin, spi_clock_frequency):

        displayio.release_displays()

        spi = busio.SPI(
            spi_clk_pin, # CLK pin
            spi_mosi_pin, # MOSI pin
            None) # MISO pin, not need to drive this display

        display_bus = displayio.FourWire(
            spi,
            command = command_pin,
            reset = reset_pin,
            chip_select = chip_select_pin, # not used but for some reason there is an error if chip_select is None
            baudrate = spi_clock_frequency)

        WIDTH = 132
        HEIGHT = 64
        BORDER = 0

        self._display = adafruit_displayio_sh1106.SH1106(display_bus, width = WIDTH, height = HEIGHT)

        # set the display to vertical mode
        self._display.rotation = 90

    @property
    def display(self):
        return self._display