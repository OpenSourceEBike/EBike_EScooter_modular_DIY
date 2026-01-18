from vars import Cfg, MotorCfg

model = 'escooter_iscooter_i12'

# Rear motor is the master on CAN, so has ID = 0
# Front motor is the first slave in CAN, so has ID = 1
rear_motor_cfg = MotorCfg(can_id=0)

# Define the CAN TX and RX pins for communications with VESC
# (VESC is a singleton in your codebase; setting on rear is enough)
rear_motor_cfg.can_rx_pin = 6
rear_motor_cfg.can_tx_pin = 5
# default VESC is 500khz, but as I was getting errors, I reduced to 125khz
rear_motor_cfg.can_baudrate = 125000
# 0 is normal mode
rear_motor_cfg.can_mode = 0

cfg = Cfg()

# Brake pin for brake sensor
cfg.brake_pin = 4

# Persist mode changes to NVS (set False to disable)
cfg.save_mode_to_nvs = False

# Right handlebar throttle
cfg.throttle_1_pin = 3            # ADC input pin
cfg.throttle_1_adc_min = 15250      # slightly above rest value
cfg.throttle_1_adc_max = 46900      # slightly below max value
cfg.throttle_1_adc_over_max_error = 54500  # safety threshold

# This board MAC Address
cfg.my_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE2]

# Display MAC Address for wireless comms
cfg.display_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE3]

#######################################################################
# If you are using a Jiabaida BMS (https://jiabaida-bms.com/) on you battery
# Keep this disabled/False as default
cfg.has_jbd_bms = False

cfg.jbd_bms_bluetooth_name = 'BMS-iScooteri12'
#######################################################################


#### Motors configurations ####

# Lunyee 2000W motor 12" has 15 pole pairs
rear_motor_cfg.poles_pair = 15

# measured as 16.5 cm, tire 3.00-8
rear_motor_cfg.wheel_radius = 0.160

# Max wheel speed in ERPM
# tire diameter: 0.33 m; tire RPM ~884; pole pairs: 15
rear_motor_cfg.motor_erpm_max_speed_limit = [
    6330,  # ≈25 km/h
    10130  # ≈40 km/h
]

# Max motor phase current limits (be careful with heating)
rear_motor_cfg.motor_max_current_limit_max = 100.0

# Minimum current to start rotation (too low → vibration/stall)
rear_motor_cfg.motor_min_current_start = 1.5

# Max regen phase current (negative = regen)
rear_motor_cfg.motor_max_current_limit_min = -80.0

# Approx 1800 W @ 72 V
rear_motor_cfg.battery_max_current_limit_max = 25.0

# Approx 500 W @ 72 V (regen)
rear_motor_cfg.battery_max_current_limit_min = -7.0


# Speed-dependent current limiting (reduce current as speed rises)
rear_motor_cfg.motor_current_limit_max_max = 100
rear_motor_cfg.motor_current_limit_max_min = 50.0
rear_motor_cfg.motor_current_limit_max_min_speed = 20.0

# Regen current vs speed
rear_motor_cfg.motor_current_limit_min_min = -70.0
rear_motor_cfg.motor_current_limit_min_max = -70.0
rear_motor_cfg.motor_current_limit_min_max_speed = 20.0

## Battery currents
rear_motor_cfg.battery_current_limit_max_max = 25.0
rear_motor_cfg.battery_current_limit_max_min = 20.0
rear_motor_cfg.battery_current_limit_max_min_speed = 20.0

# Regen battery current limits
rear_motor_cfg.battery_current_limit_min_min = -7.0
rear_motor_cfg.battery_current_limit_min_max = -5.25
rear_motor_cfg.battery_current_limit_min_max_speed = 20.0
