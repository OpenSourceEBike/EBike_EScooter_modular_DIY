import board
from vars import Cfg, MotorCfg
cfg = Cfg()

# Rear motor is the master on CAN, so has ID = 0
# Front motor is the first slave in CAN, so has ID = 1
rear_motor_cfg = MotorCfg(can_id=0)
front_motor_cfg = MotorCfg(can_id=1)

# Define the CAN TX and RX pins for communications with Vesc
# and set them on rear_motor_cfg, that will be ok as VESC is a Singleton
rear_motor_cfg.can_rx_pin = board.IO4
rear_motor_cfg.can_tx_pin = board.IO5

# Brake for brake sensor
cfg.brake_pin = board.IO12

# Right handlebar throttle
cfg.throttle_1_pin = board.IO11 # ADC input pin
cfg.throttle_1_adc_min = 17000 # this is a value that should be a bit superior than the min value, so if throttle is in rest position, motor will not run
cfg.throttle_1_adc_max = 49800 # this is a value that should be a bit lower than the max value, so if throttle is at max position, the calculated value of throttle will be the max
cfg.throttle_1_adc_over_max_error = 54500 # this is a value that should be a bit superior than the max value, just to protect is the case there is some issue with the signal and then motor can keep run at max speed!!

# Left handlebar throttle
cfg.throttle_2_pin = board.IO10
cfg.throttle_2_adc_min = 18000
cfg.throttle_2_adc_max = 49000
cfg.throttle_2_adc_over_max_error = 54500

# This board MAC Address
cfg.my_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf2]

# MAC Address value needed for the wireless communication with the display
cfg.display_mac_address = [0x68, 0xb6, 0xb3, 0x01, 0xf7, 0xf3]


#### Motors configurations ####

# Lunyee 2000W motor 12 inches (not the original Fiido Q1S motor) has 15 poles pair
front_motor_cfg.poles_pair = 15
rear_motor_cfg.poles_pair = 15

# measured as 16.5cms, 3.00-8 tire
rear_motor_cfg.wheel_radius = 0.165

# max wheel speed in ERPM
# tire diameter: 0.33 meters
# tire RPM: 884
# motor poles: 15
# motor ERPM: 13263 to get 55kms/h wheel speedfront_motor_data.motor_poles_pair = 15
# 55kms/h
front_motor_cfg.motor_erpm_max_speed_limit = 13263 
rear_motor_cfg.motor_erpm_max_speed_limit = 13263

 # max value, be careful to not burn your motor
front_motor_cfg.motor_max_current_limit_max = 150.0
rear_motor_cfg.motor_max_current_limit_max = 135.0

# to much lower value will make the motor vibrate and not run, so, impose a min limit (??)
front_motor_cfg.motor_min_current_start = 4.0
rear_motor_cfg.motor_min_current_start = 1.5

# max regen current
front_motor_cfg.motor_max_current_limit_min = -80.0 
rear_motor_cfg.motor_max_current_limit_min = -80.0

# about 1000W at 72V
front_motor_cfg.battery_max_current_limit_max = 15.0
rear_motor_cfg.battery_max_current_limit_max = 15.0

# about 500W at 72V
front_motor_cfg.battery_max_current_limit_min = -7.0 
rear_motor_cfg.battery_max_current_limit_min = -7.0


# To reduce motor temperature, motor current limits are higher at startup and low at higer speeds
# motor current limits will be adjusted on this values, depending on the speed
# like at startup will have 'motor_current_limit_max_max' and then will reduce linearly
# up to the 'motor_current_limit_max_min', when wheel speed is
# 'motor_current_limit_max_min_speed'
front_motor_cfg.motor_current_limit_max_max = 35.0 # front motor start with low current to avoid skidding
front_motor_cfg.motor_current_limit_max_min = 80.0
front_motor_cfg.motor_current_limit_max_min_speed = 30.0

rear_motor_cfg.motor_current_limit_max_max = 120.0
rear_motor_cfg.motor_current_limit_max_min = 50.0
rear_motor_cfg.motor_current_limit_max_min_speed = 30.0

# this are the values for regen
front_motor_cfg.motor_current_limit_min_min = -50.0
front_motor_cfg.motor_current_limit_min_max = -50.0
front_motor_cfg.motor_current_limit_min_max_speed = 30.0

rear_motor_cfg.motor_current_limit_min_min = -60.0
rear_motor_cfg.motor_current_limit_min_max = -60.0
rear_motor_cfg.motor_current_limit_min_max_speed = 30.0

## Battery currents
# Max total: 30A --> 2000W

# the idea is to have a higher power at startup on rear motor and lower at front motor,
# then gradually shiffing the power
front_motor_cfg.battery_current_limit_max_max = 10.0 # about 700W at 72V
front_motor_cfg.battery_current_limit_max_min = 12.5 # about 900W at 72V
front_motor_cfg.battery_current_limit_max_min_speed = 30.0

rear_motor_cfg.battery_current_limit_max_max = 20.0 # about 1400W at 72V
rear_motor_cfg.battery_current_limit_max_min = 15.0 # about 1100W at 72V
rear_motor_cfg.battery_current_limit_max_min_speed = 30.0

# this are the values for regen
# Max regen total: 14A --> 1000W
# Min regen total: 10.5A --> 800W
front_motor_cfg.battery_current_limit_min_min = -7.0
front_motor_cfg.battery_current_limit_min_max = -5.25 # about 25% less
front_motor_cfg.battery_current_limit_min_max_speed = 30.0

rear_motor_cfg.battery_current_limit_min_min = -7.0
rear_motor_cfg.battery_current_limit_min_max = -5.25 # about 25% less
rear_motor_cfg.battery_current_limit_min_max_speed = 30.0
