# iScooter i12 config (display + main board + lights + APC)

from common.config_main_board_common import Cfg, MotorCfg

# ===================================================================
# MAC ADDRESSES (all boards)
# ===================================================================
mac_address_display       = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE3]
mac_address_power_switch  = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE1]
mac_address_motor_board   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE2]
mac_address_rear_lights   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE4]
mac_address_front_lights  = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE5]

# ===================================================================
# MAIN BOARD CONFIGS
# ===================================================================
rear_motor_cfg = MotorCfg(can_id=0)
front_motor_cfg = None

rear_motor_cfg.can_rx_pin = 6
rear_motor_cfg.can_tx_pin = 5
rear_motor_cfg.can_baudrate = 125000
rear_motor_cfg.can_mode = 0

cfg = Cfg()

cfg.brake_pin = 4
cfg.save_mode_to_nvs = False

# Right handlebar throttle
cfg.throttle_1_pin = 3
cfg.throttle_1_adc_min = 15250
cfg.throttle_1_adc_max = 46900
cfg.throttle_1_adc_over_max_error = 54500

# Main board and display MACs
cfg.my_mac_address = mac_address_motor_board
cfg.display_mac_address = mac_address_display

# JBD BMS
cfg.has_jbd_bms = False
cfg.jbd_bms_bluetooth_name = 'BMS-iScooteri12'

# Motors
rear_motor_cfg.poles_pair = 15
rear_motor_cfg.wheel_radius = 0.160

rear_motor_cfg.motor_erpm_max_speed_limit = [
    6330,   # ≈25 km/h
    10130   # ≈40 km/h
]

rear_motor_cfg.vesc_min_temperature_x10 = 400
rear_motor_cfg.vesc_max_temperature_x10 = 1000
rear_motor_cfg.min_temperature_x10 = 400
rear_motor_cfg.max_temperature_x10 = 1000

rear_motor_cfg.motor_max_current_limit_max = 100.0
rear_motor_cfg.motor_min_current_start = 1.5
rear_motor_cfg.motor_max_current_limit_min = -80.0

rear_motor_cfg.battery_max_current_limit_max = 25.0
rear_motor_cfg.battery_max_current_limit_min = -8.0

# Speed-dependent current limiting
rear_motor_cfg.motor_current_limit_max_max = 100.0
rear_motor_cfg.motor_current_limit_max_min = 50.0
rear_motor_cfg.motor_current_limit_max_min_speed = 20.0

# Regen current vs speed
rear_motor_cfg.motor_current_limit_min_min = -70.0
rear_motor_cfg.motor_current_limit_min_max = -70.0
rear_motor_cfg.motor_current_limit_min_max_speed = 20.0

# Battery current limits
rear_motor_cfg.battery_current_limit_max_max = 25.0
rear_motor_cfg.battery_current_limit_max_min = 20.0
rear_motor_cfg.battery_current_limit_max_min_speed = 20.0

# Regen battery current limits
rear_motor_cfg.battery_current_limit_min_min = -10.0
rear_motor_cfg.battery_current_limit_min_max = -8.0
rear_motor_cfg.battery_current_limit_min_max_speed = 20.0

# ===================================================================
# DISPLAY / LIGHTS / APC CONFIGS
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

# Nominal battery voltage for display power estimates
battery_voltage = 72.0

# Motor power scaling (W) for display
motor_power_max_w = rear_motor_cfg.battery_current_limit_max_min * battery_voltage
motor_regen_power_max_w = rear_motor_cfg.battery_current_limit_min_max * battery_voltage
