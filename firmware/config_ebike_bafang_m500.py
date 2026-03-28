# Bafang M500 config (display + main board + lights + APC)

from common.model_constants import (
  TYPE_EBIKE,
  MOTOR_SINGLE,
)

type = {
  "ebike_escooter": TYPE_EBIKE,
  "single_dual_moor": MOTOR_SINGLE,
}

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

# Enable reading date/time from the external RTC chip (DS3231).
enable_rtc_time = True
# I2C pins used by the RTC chip.
rtc_scl_pin = 8
rtc_sda_pin = 7
# Required timezone name used to select UTC offset and DST rules.
rtc_timezone = "Europe/Lisbon"
# Verbose RTC initialization and WiFi/NTP sync logging.
rtc_debug = False
# Backlight auto-off while staying on idle display screens.
backlight_timeout_ms = 1000
# Auto-return from Main to Boot after inactivity.
main_screen_timeout_ms = 300000

# Power button pin (active-low with PULL_UP)
power_button_pin = 6
lights_button_pin = 5

# Long-press
power_btn_long_ms = 700
debounce_ms = 30

# Tail light brake blink (for scooters without a dedicated brake light)
brake_tail_blink_enable = True
brake_tail_on_ms = 400
brake_tail_off_ms = 100

# TODO: fill in ESP-NOW MACs and motor power scaling
