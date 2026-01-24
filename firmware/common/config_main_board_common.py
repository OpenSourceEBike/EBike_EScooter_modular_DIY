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
