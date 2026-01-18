class Cfg(object):
    def __init__(self):
        self.throttle_1_adc_min = 0
        self.throttle_1_adc_max = 0
        self.throttle_1_adc_over_max_error = 0
        self.throttle_2_adc_min = 0
        self.throttle_2_adc_max = 0
        self.throttle_2_adc_over_max_error = 0
        self.my_mac_address = 0
        self.display_mac_address = 0
        self.has_jbd_bms = False
        self.jbd_bms_bluetooth_name = ''
        self.charge_current_threshold_a_x100 = 0
        self.charge_detect_hold_ms = 0
        self.save_mode_to_nvs = False

class MotorCfg(object):
    def __init__(self, can_id):
        self.can_id = can_id
        self.can_tx_pin = None
        self.can_rx_pin = None       
        self.can_baudrate = None
        self.can_mode = None
        self.poles_pair = 0
        self.wheel_radius = 0
        self.motor_current_limit_max_max = 0
        self.motor_current_limit_max_min = 0
        self.motor_current_limit_max_min_speed = 0
        self.motor_current_limit_min_max_speed = 0
        self.motor_current_limit_min_max = 0
        self.motor_current_limit_min_min = 0
        self.battery_current_limit_max_max = 0
        self.battery_current_limit_max_min = 0
        self.battery_current_limit_max_min_speed = 0
        self.battery_current_limit_min_max_speed = 0
        self.battery_current_limit_min_max = 0
        self.battery_current_limit_min_min = 0
        self.motor_erpm_max_speed_limit = 0
        self.motor_max_current_limit_max = 0
        self.motor_min_current_start = 0
        self.motor_max_current_limit_min = 0
        self.battery_max_current_limit_max = 0
        self.battery_max_current_limit_min = 0
        
class CruiseControl(object):
    def __init__(self):
        self.state = 0
        self.button_long_press_previous_state = 0
        self.button_press_previous_state = 0
        self.throttle_value = 0

class Vars(object):
    def __init__(self):
        self.motor_current_x100 = 0
        self.motor_power = 0
        self.motor_temperature_sensor_x10 = 0
        self.brakes_are_active = True
        self.regen_braking_is_active = False
        self.torque_weight_x10 = 0
        self.cadence = 0
        self.assist_level = 0
        self.throttle_value = 0
        self.brakes_value = 0
        self.motors_enable_state = False
        self.buttons_state = 0
        self.cruise_control = CruiseControl()
        self.bms_battery_current_x100 = None
        self.battery_is_charging = False
        self.mode = 0
        
