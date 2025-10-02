from vars import Cfg, MotorCfg

cfg = Cfg()

# Rear motor is the master on CAN, so has ID = 0
# Front motor is the first slave in CAN, so has ID = 1
rear_motor_cfg = MotorCfg(can_id=0)
front_motor_cfg = MotorCfg(can_id=1)

# Define the CAN TX and RX pins for communications with VESC
# (VESC is a singleton in your codebase; setting on rear is enough)
rear_motor_cfg.can_rx_pin = 3
rear_motor_cfg.can_tx_pin = 2

# Brake pin for brake sensor
cfg.brake_pin = 4

# Right handlebar throttle
cfg.throttle_1_pin = 0            # ADC input pin
cfg.throttle_1_adc_min = 18500      # slightly above rest value
cfg.throttle_1_adc_max = 55600      # slightly below max value
cfg.throttle_1_adc_over_max_error = 54500  # safety threshold

# Left handlebar throttle
cfg.throttle_2_pin = 1
cfg.throttle_2_adc_min = 18700
cfg.throttle_2_adc_max = 54500
cfg.throttle_2_adc_over_max_error = 54500

# This board MAC Address
cfg.my_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF2]

# Display MAC Address for wireless comms
cfg.display_mac_address = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF3]


#### Motors configurations ####

# Lunyee 2000W motor 12" has 15 pole pairs
front_motor_cfg.poles_pair = 15
rear_motor_cfg.poles_pair = 15

# measured as 16.5 cm, tire 3.00-8
rear_motor_cfg.wheel_radius = 0.165

# Max wheel speed in ERPM
# tire diameter: 0.33 m; tire RPM ~884; pole pairs: 15 → ERPM ≈ 13263 for ~55 km/h
front_motor_cfg.motor_erpm_max_speed_limit = 13263
rear_motor_cfg.motor_erpm_max_speed_limit = 13263

# Max motor phase current limits (be careful with heating)
front_motor_cfg.motor_max_current_limit_max = 150.0
rear_motor_cfg.motor_max_current_limit_max = 135.0

# Minimum current to start rotation (too low → vibration/stall)
front_motor_cfg.motor_min_current_start = 4.0
rear_motor_cfg.motor_min_current_start = 1.5

# Max regen phase current (negative = regen)
front_motor_cfg.motor_max_current_limit_min = -80.0
rear_motor_cfg.motor_max_current_limit_min = -80.0

# Approx 1000 W @ 72 V
front_motor_cfg.battery_max_current_limit_max = 15.0
rear_motor_cfg.battery_max_current_limit_max = 15.0

# Approx 500 W @ 72 V (regen)
front_motor_cfg.battery_max_current_limit_min = -7.0
rear_motor_cfg.battery_max_current_limit_min = -7.0


# Speed-dependent current limiting (reduce current as speed rises)
# Front motor starts softer to avoid skidding
front_motor_cfg.motor_current_limit_max_max = 35.0
front_motor_cfg.motor_current_limit_max_min = 80.0
front_motor_cfg.motor_current_limit_max_min_speed = 30.0  # km/h (your logic unit)

rear_motor_cfg.motor_current_limit_max_max = 120.0
rear_motor_cfg.motor_current_limit_max_min = 50.0
rear_motor_cfg.motor_current_limit_max_min_speed = 30.0

# Regen current vs speed
front_motor_cfg.motor_current_limit_min_min = -50.0
front_motor_cfg.motor_current_limit_min_max = -50.0
front_motor_cfg.motor_current_limit_min_max_speed = 30.0

rear_motor_cfg.motor_current_limit_min_min = -60.0
rear_motor_cfg.motor_current_limit_min_max = -60.0
rear_motor_cfg.motor_current_limit_min_max_speed = 30.0

## Battery currents (totals target around 30 A → ~2000 W)

# Shift more power to rear at launch, then balance with speed
front_motor_cfg.battery_current_limit_max_max = 10.0   # ~700 W @ 72 V
front_motor_cfg.battery_current_limit_max_min = 12.5   # ~900 W @ 72 V
front_motor_cfg.battery_current_limit_max_min_speed = 30.0

rear_motor_cfg.battery_current_limit_max_max = 20.0    # ~1400 W @ 72 V
rear_motor_cfg.battery_current_limit_max_min = 15.0    # ~1100 W @ 72 V
rear_motor_cfg.battery_current_limit_max_min_speed = 30.0

# Regen battery current limits
# Max regen total ~14 A (~1000 W); min regen total ~10.5 A (~800 W)
front_motor_cfg.battery_current_limit_min_min = -7.0
front_motor_cfg.battery_current_limit_min_max = -5.25  # ~25% less
front_motor_cfg.battery_current_limit_min_max_speed = 30.0

rear_motor_cfg.battery_current_limit_min_min = -7.0
rear_motor_cfg.battery_current_limit_min_max = -5.25   # ~25% less
rear_motor_cfg.battery_current_limit_min_max_speed = 30.0
