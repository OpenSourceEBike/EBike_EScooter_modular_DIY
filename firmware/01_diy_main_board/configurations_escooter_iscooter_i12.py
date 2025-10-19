from vars import Cfg, MotorCfg

cfg = Cfg()

# Rear motor is the master on CAN, so has ID = 0
# Front motor is the first slave in CAN, so has ID = 1
rear_motor_cfg = MotorCfg(can_id=0)
front_motor_cfg = MotorCfg(can_id=1)

# Define the CAN TX and RX pins for communications with VESC
# (VESC is a singleton in your codebase; setting on rear is enough)
rear_motor_cfg.can_rx_pin = 6
rear_motor_cfg.can_tx_pin = 5
# default VESC is 500khz, but as I was getting errors, I reduced to 125khz
rear_motor_cfg.can_baudrate = 125000
# 0 is normal mode
rear_motor_cfg.can_mode = 0

# Brake pin for brake sensor
cfg.brake_pin = 4

# Right handlebar throttle
cfg.throttle_1_pin = 3            # ADC input pin
cfg.throttle_1_adc_min = 15250      # slightly above rest value
cfg.throttle_1_adc_max = 46900      # slightly below max value
cfg.throttle_1_adc_over_max_error = 54500  # safety threshold

# This board MAC Address
cfg.my_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF2]

# Display MAC Address for wireless comms
cfg.display_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF3]

#######################################################################
# If you are using a Jiabaida BMS (https://jiabaida-bms.com/) on you battery
# Keep this disabled/False as default
cfg.has_jbd_bms = False

cfg.jbd_bms_bluetooth_name = 'BMS-FiidoQ1S'
#######################################################################


#### Motors configurations ####

# iScooter i12 motor 12" has 20 pole pairs
front_motor_cfg.poles_pair = 20
rear_motor_cfg.poles_pair = 20

# TODO: verify
rear_motor_cfg.wheel_radius = 0.165

# Max wheel speed in ERPM
# 1000 --> ~30 km/h
front_motor_cfg.motor_erpm_max_speed_limit = 10000
rear_motor_cfg.motor_erpm_max_speed_limit = 10000

# Max motor phase current limits (be careful with heating)
front_motor_cfg.motor_max_current_limit_max = 90.0
rear_motor_cfg.motor_max_current_limit_max = 90.0

# Minimum current to start rotation (too low → vibration/stall)
front_motor_cfg.motor_min_current_start = 2.0
rear_motor_cfg.motor_min_current_start = 2.0

# Max regen phase current (negative = regen)
front_motor_cfg.motor_max_current_limit_min = -50.0
rear_motor_cfg.motor_max_current_limit_min = -50.0

# Approx 1000 W @ 72 V
front_motor_cfg.battery_max_current_limit_max = 30.0
rear_motor_cfg.battery_max_current_limit_max = 30.0

# Approx 500 W @ 72 V (regen)
front_motor_cfg.battery_max_current_limit_min = -5.0
rear_motor_cfg.battery_max_current_limit_min = -5.0


# Speed-dependent current limiting (reduce current as speed rises)
# Front motor starts softer to avoid skidding
front_motor_cfg.motor_current_limit_max_max = 90.0
front_motor_cfg.motor_current_limit_max_min = 66.0
front_motor_cfg.motor_current_limit_max_min_speed = 15.0  # km/h (your logic unit)

rear_motor_cfg.motor_current_limit_max_max = 90.0
rear_motor_cfg.motor_current_limit_max_min = 66.0
rear_motor_cfg.motor_current_limit_max_min_speed = 15.0

# Regen current vs speed
front_motor_cfg.motor_current_limit_min_min = -40.0
front_motor_cfg.motor_current_limit_min_max = -40.0
front_motor_cfg.motor_current_limit_min_max_speed = 15.0

rear_motor_cfg.motor_current_limit_min_min = -40.0
rear_motor_cfg.motor_current_limit_min_max = -40.0
rear_motor_cfg.motor_current_limit_min_max_speed = 15.0

## Battery currents (totals target around 30 A → ~2000 W)

# Shift more power to rear at launch, then balance with speed
front_motor_cfg.battery_current_limit_max_max = 30.0   # ~700 W @ 72 V
front_motor_cfg.battery_current_limit_max_min = 25.0   # ~900 W @ 72 V
front_motor_cfg.battery_current_limit_max_min_speed = 15.0

rear_motor_cfg.battery_current_limit_max_max = 30.0    # ~1400 W @ 72 V
rear_motor_cfg.battery_current_limit_max_min = 25.0    # ~1100 W @ 72 V
rear_motor_cfg.battery_current_limit_max_min_speed = 15.0

# Regen battery current limits
# Max regen total ~14 A (~1000 W); min regen total ~10.5 A (~800 W)
front_motor_cfg.battery_current_limit_min_min = -5.0
front_motor_cfg.battery_current_limit_min_max = -4.0
front_motor_cfg.battery_current_limit_min_max_speed = 15.0

rear_motor_cfg.battery_current_limit_min_min = -5.0
rear_motor_cfg.battery_current_limit_min_max = -4.0
rear_motor_cfg.battery_current_limit_min_max_speed = 15.0
