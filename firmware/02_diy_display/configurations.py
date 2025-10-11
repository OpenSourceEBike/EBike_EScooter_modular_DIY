from micropython import const

# ESPNow wireless communications uses this MAC address
my_mac_address             = b"\x68\xb6\xb3\x01\xf7\xf3"  # display
mac_address_power_switch   = b"\x68\xb6\xb3\x01\xf7\xf1"
mac_address_motor_board    = b"\x68\xb6\xb3\x01\xf7\xf2"
mac_address_rear_lights    = b"\x68\xb6\xb3\x01\xf7\xf4"
mac_address_front_lights   = b"\x68\xb6\xb3\x01\xf7\xf5"

# ---- ST7565 pins from your main.py ----
pin_spi_clk   = const(3)   # SCK
pin_spi_mosi  = const(4)   # MOSI
pin_cs    = const(1)
pin_dc    = const(2)
pin_rst   = const(0)
pin_bl    = const(21)

spi_baud  = const(10_000_000)

# Power button pin (active-low with PULL_UP)
power_btn_pin = const(5)

# Long-press
power_btn_long_ms = const(700)
debounce_ms       = const(30)

# Charging detection
charge_current_threshold_a = const(2)
charge_detect_hold_ms      = const(2000)

# UI
ui_hz = const(10)
poweroff_countdown_s = const(3)
wheel_stop_kmh = const(0)
