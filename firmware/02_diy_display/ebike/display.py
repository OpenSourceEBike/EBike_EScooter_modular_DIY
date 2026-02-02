from lcd.lcd_st7565 import LCD


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
  ):
    self._lcd = LCD(
      spi_clk_pin=spi_clk_pin,
      spi_mosi_pin=spi_mosi_pin,
      chip_select_pin=chip_select_pin,
      command_pin=command_pin,
      reset_pin=reset_pin,
      backlight_pin=backlight_pin,
      spi_clock_frequency=spi_clock_frequency,
    )
    self.display = self._lcd.display
