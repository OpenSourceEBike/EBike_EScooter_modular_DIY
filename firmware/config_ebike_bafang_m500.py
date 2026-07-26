# Bafang M500 config (legacy / not maintained).
#
# The e-bike firmware path is kept as historical reference only. It is not
# aligned with the current MicroPython ESP-NOW protocol, shared config loader,
# or active scooter board topology.

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
bms_debug = False

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

# RTC date/time feature and settings.
# This feature is optional and can be ignored.
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

# Button duration windows
power_btn_click_min_ms = 200
power_btn_long_ms = 1000
debounce_ms = 30

# Tail light brake blink (for scooters without a dedicated brake light)
brake_tail_blink_enable = True
brake_tail_on_ms = 400
brake_tail_off_ms = 100

# Automatic Power Control board defaults.
# This board/feature is optional and can be ignored. In that case,
# motion_detection_threshold: 0..255
#   12 = current configured value (more sensitive than 16)
#   16 = fairly sensitive, common starting point
#   32 = moderate
#   64 = hard to trigger
#   127 = very hard to trigger
#   255 = maximum threshold, hardest to trigger
# motion_detection_rate_hz: 3, 6, 12, 25, 50, 100, 200, 400, 800, 1600, 3200
#   default 25; unsupported values are rounded to the nearest supported rate
motion_detection_threshold = 12
motion_detection_rate_hz = 25
motion_detection_ac_mode = True
timeout_no_motion_seconds_to_disable_relay = 300
seconds_to_wait_before_movement_detection = 20

# TODO: fill in ESP-NOW MACs and motor power scaling
