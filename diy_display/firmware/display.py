import busio
import displayio
import displayio_st7565
import pwmio
import digitalio

displayio.release_displays()

class Display(object):
    def __init__(self, spi_clk_pin, spi_mosi_pin, chip_select_pin, command_pin, reset_pin, backlight_pin, spi_clock_frequency):

        spi = busio.SPI(
            spi_clk_pin, # CLK pin
            spi_mosi_pin, # MOSI pin
            None) # MISO pinin, not need to drive this display
        
        display_bus = displayio.FourWire(
            spi, command=command_pin, chip_select=chip_select_pin, reset=reset_pin, baudrate=spi_clock_frequency
        )
        
        self._display = displayio_st7565.ST7565(display_bus, width=128, height=64)
                
        self._backlight = pwmio.PWMOut(backlight_pin, frequency=1000)
        self.backlight_pwm(0.6)
        self._display.reverse = False
        self._display.contrast = 0

    @property
    def display(self):
        return self._display
    
    def backlight_pwm(self, duty_cycle_percent=0.5):
        # The display backlight has inverted state, 0 logic backlight enabled
        value = 65535 * duty_cycle_percent
        
        if value > 65535:
            value = 65535
            
        if value < 0:
            value = 0
        
        self._backlight.duty_cycle = int(65535 - value)