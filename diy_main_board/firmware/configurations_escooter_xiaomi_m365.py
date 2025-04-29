import board
from vars import Cfg, MotorCfg
cfg = Cfg()

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

# Define the CAN TX and RX pins for communications with Vesc
front_motor_cfg.can_rx_pin = board.IO4
front_motor_cfg.can_tx_pin = board.IO5

# Brake analog pin
cfg.brake_pin = board.IO11 # ADC input pin
cfg.brake_analog_adc_min = 12000 # this is a value that should be a bit superior than the min value, so if throttle is in rest position, motor will not run
cfg.brake_analog_adc_max = 55000 # this is a value that should be a bit lower than the max value, so if throttle is at max position, the calculated value of throttle will be the max
cfg.brake_analog_adc_over_max_error = 58000 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

# Throttle
cfg.throttle_1_pin = board.IO10
cfg.throttle_1_adc_min = 11500
cfg.throttle_1_adc_max = 55000
cfg.throttle_1_adc_over_max_error = 58000

# This board MAC Address
cfg.my_mac_address = [0x00, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]

# MAC Address value needed for the wireless communication with the display
cfg.display_mac_address = [0x00, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]


#### Motor configurations ####

# Original M365 motor has 15 pole pairs
front_motor_cfg.poles_pair = 15

# M365 10 inches wheels has 120mm radius
front_motor_cfg.wheel_radius = 0.120

# Max wheel speed in ERPM
# 12200 erpm --> 36.7 km/h
front_motor_cfg.motor_erpm_max_speed_limit = 12200

# Max motor regen current
# Assuming motor current = 4 * battery current
front_motor_cfg.motor_max_current_limit_max = 40.0
front_motor_cfg.motor_max_current_limit_min = -20.0