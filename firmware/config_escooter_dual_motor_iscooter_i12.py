# Fiido Q1S config (display + main board + lights + APC)

from common.model_constants import (
  TYPE_ESCOOTER,
  MOTOR_DUAL,
)
from common.config_main_board_common import Cfg, MotorCfg

type = {
  "ebike_escooter": TYPE_ESCOOTER,
  "single_dual_moor": MOTOR_DUAL,
}

# ===================================================================
# MAC ADDRESSES (all boards)
# ===================================================================
mac_address_display       = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF3]
mac_address_power_switch  = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF1]
mac_address_motor_board   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF2]
mac_address_lights        = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF4]

# ===================================================================
# MAIN BOARD CONFIGS
# ===================================================================
rear_motor_cfg = MotorCfg(can_id=0)
front_motor_cfg = MotorCfg(can_id=1)

rear_motor_cfg.can_rx_pin = 6
rear_motor_cfg.can_tx_pin = 5
rear_motor_cfg.can_baudrate = 125000
rear_motor_cfg.can_mode = 0

cfg = Cfg()

# Store mode / speed limit
cfg.save_mode_to_nvs = True

cfg.brake_pin = 4

# Right handlebar throttle
cfg.throttle_1_pin = 3
cfg.throttle_1_adc_min = 16600
cfg.throttle_1_adc_max = 49500
cfg.throttle_1_adc_over_max_error = 54500

# Left handlebar throttle
cfg.throttle_2_pin = 2
cfg.throttle_2_adc_min = 16600
cfg.throttle_2_adc_max = 48500
cfg.throttle_2_adc_over_max_error = 54500

# JBD BMS
cfg.has_jbd_bms = True
cfg.jbd_bms_bluetooth_name = 'BMS-FiidoQ1S'

# Charging detection
cfg.charge_current_threshold_a_x100 = 50
cfg.charge_detect_hold_ms = 1000

# Motors
front_motor_cfg.poles_pair = 15
rear_motor_cfg.poles_pair = 15

rear_motor_cfg.wheel_radius = 0.165

rear_motor_cfg.motor_erpm_max_speed_limit = [
  6330,   # ≈25 km/h
  13263   # ≈55 km/h
]

front_motor_cfg.motor_erpm_max_speed_limit = [
  6330,   # ≈25 km/h
  13263   # ≈55 km/h
]

rear_motor_cfg.vesc_min_temperature_x10 = 850
rear_motor_cfg.vesc_max_temperature_x10 = 1000
rear_motor_cfg.min_temperature_x10 = 700
rear_motor_cfg.max_temperature_x10 = 1100

front_motor_cfg.motor_max_current_limit_max = 100.0
rear_motor_cfg.motor_max_current_limit_max = 100.0

front_motor_cfg.motor_min_current_start = 1.5
rear_motor_cfg.motor_min_current_start = 1.5

front_motor_cfg.motor_max_current_limit_min = -100.0
rear_motor_cfg.motor_max_current_limit_min = -100.0

front_motor_cfg.battery_max_current_limit_max = 20.0
rear_motor_cfg.battery_max_current_limit_max = 20.0

front_motor_cfg.battery_max_current_limit_min = -7.0
rear_motor_cfg.battery_max_current_limit_min = -7.0

# Speed-dependent current limiting
front_motor_cfg.motor_current_limit_max_max = 30.0
front_motor_cfg.motor_current_limit_max_min = 40.0
front_motor_cfg.motor_current_limit_max_min_speed = 25.0

rear_motor_cfg.motor_current_limit_max_max = 100.0
rear_motor_cfg.motor_current_limit_max_min = 35.0
rear_motor_cfg.motor_current_limit_max_min_speed = 25.0

# Regen current vs speed
front_motor_cfg.motor_current_limit_min_min = -35.0
front_motor_cfg.motor_current_limit_min_max = -35.0
front_motor_cfg.motor_current_limit_min_max_speed = 25.0

rear_motor_cfg.motor_current_limit_min_min = -45.0
rear_motor_cfg.motor_current_limit_min_max = -45.0
rear_motor_cfg.motor_current_limit_min_max_speed = 25.0

# Battery current limits
front_motor_cfg.battery_current_limit_max_max = 10.0
front_motor_cfg.battery_current_limit_max_min = 12.5
front_motor_cfg.battery_current_limit_max_min_speed = 25.0

rear_motor_cfg.battery_current_limit_max_max = 20.0
rear_motor_cfg.battery_current_limit_max_min = 15.0
rear_motor_cfg.battery_current_limit_max_min_speed = 25.0

# Regen battery current limits
front_motor_cfg.battery_current_limit_min_min = -6.0
front_motor_cfg.battery_current_limit_min_max = -6.0
front_motor_cfg.battery_current_limit_min_max_speed = 25.0

rear_motor_cfg.battery_current_limit_min_min = -6.0
rear_motor_cfg.battery_current_limit_min_max = -6.0
rear_motor_cfg.battery_current_limit_min_max_speed = 25.0

# ===================================================================
# DISPLAY
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
rtc_timezone = "Europe/Lisbon"

# Power button pin (active-low with PULL_UP)
power_button_pin = 6
lights_button_pin = 5

# Long-press
power_btn_long_ms = 700
debounce_ms = 30

# Nominal battery voltage for display power estimates
battery_voltage = 72.0

# Motor power scaling (W) for display
motor_power_max_w = (front_motor_cfg.battery_current_limit_max_min + \
          rear_motor_cfg.battery_current_limit_max_min) \
          * battery_voltage
          
motor_regen_power_max_w = (front_motor_cfg.battery_current_limit_min_max + \
          rear_motor_cfg.battery_current_limit_min_max) \
          * battery_voltage

# Tail light brake blink (for scooters without a dedicated brake light)
tail_always_enabled = True
brake_tail_blink_enable = True
brake_tail_on_ms = 400
brake_tail_off_ms = 100
