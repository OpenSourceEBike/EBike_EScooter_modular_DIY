from vars import Cfg, MotorCfg

model = 'escooter_xiaomi_m365'

assist_level_factor_table = [
    0,
    0.13,
    0.16,
    0.20,
    0.24,
    0.31,
    0.38,
    0.48,
    0.60,
    0.75,
    0.93,
    1.16,
    1.46,
    1.82,
    2.27,
    2.84,
    3.55,
    4.44,
    5.55,
    6.94,
    8.67
]

# Front motor is the master on CAN, so has ID = 0
front_motor_cfg = MotorCfg(can_id=0)

# CAN pins for VESC comms
front_motor_cfg.can_rx_pin = 4
front_motor_cfg.can_tx_pin = 5

cfg = Cfg()

# Brake (analog) pin + thresholds
cfg.brake_pin = 11  # ADC input pin
cfg.brake_analog_adc_min = 12000
cfg.brake_analog_adc_max = 55000
cfg.brake_analog_adc_over_max_error = 58000

# Throttle (analog) pin + thresholds
cfg.throttle_1_pin = 10
cfg.throttle_1_adc_min = 11500
cfg.throttle_1_adc_max = 55000
cfg.throttle_1_adc_over_max_error = 58000

# MAC addresses
cfg.my_mac_address      = [0x00, 0xB6, 0xB3, 0x01, 0xF7, 0xF2]
cfg.display_mac_address = [0x00, 0xB6, 0xB3, 0x01, 0xF7, 0xF3]

#### Motor configurations ####

# Original M365 motor
front_motor_cfg.poles_pair = 15

# M365 10" wheel radius (m)
front_motor_cfg.wheel_radius = 0.120

# Max wheel speed in ERPM (≈36.7 km/h)
front_motor_cfg.motor_erpm_max_speed_limit = 12200

# Motor current limits (phase current; negative = regen)
# Assuming motor current ≈ 4 × battery current
front_motor_cfg.motor_max_current_limit_max = 40.0
front_motor_cfg.motor_max_current_limit_min = -20.0
