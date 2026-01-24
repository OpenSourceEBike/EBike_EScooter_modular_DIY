# Bafang M500 config (display + main board + lights + APC)

# ===================================================================
# MAC ADDRESSES (all boards)
# ===================================================================
# TODO: fill in MACs for display, power switch, motor board, lights

# ===================================================================
# MAIN BOARD CONFIGS
# (All values used by 01_diy_main_board live in this section)
# ===================================================================
# TODO: fill in main board configs for Bafang M500

# ===================================================================
# DISPLAY / LIGHTS / APC CONFIGS
# (All values used by 02_diy_display, 03_diy_lights_board,
#  and 04_diy_automatic_power_control live in this section)
# ===================================================================
# LCD ST7565 pins
pin_spi_mosi = 43
pin_spi_clk = 44
pin_dc = 13
pin_cs = 12
pin_rst = 11
pin_bl = 10

spi_baud = 10_000_000

enable_rtc_time = True
rtc_scl_pin = 8
rtc_sda_pin = 7

# Power button pin (active-low with PULL_UP)
power_button_pin = 6
lights_button_pin = 5

# Long-press
power_btn_long_ms = 700
debounce_ms = 30

# TODO: fill in ESP-NOW MACs and motor power scaling
