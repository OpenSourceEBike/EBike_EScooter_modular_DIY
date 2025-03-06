import time


        # self.can_id = None
        # self.uart_tx_pin = None
        # self.uart_rx_pin = None
        # self.uart_baudrate = None

class MotorSingleDual:
    SINGLE = 0
    DUAL = 1

class MotorControlScheme:
    SPEED = 0
    SPEED_NO_REGEN = 1

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

class MotorCfg(object):
    def __init__(self, motor_number):
        self.number = motor_number
        self.poles_pair = 0
        self.motor_current_limit_max_max = 0
        self.motor_current_limit_max_min = 0
        self.motor_current_limit_max_min_speed = 0
        self.motor_current_limit_min_max = 0
        self.motor_current_limit_min_min = 0
        self.motor_current_limit_min_min_speed = 0
        self.battery_current_limit_max_max = 0
        self.battery_current_limit_max_min = 0
        self.battery_current_limit_max_min_speed = 0
        self.battery_current_limit_min_max = 0
        self.battery_current_limit_min_min = 0
        self.battery_current_limit_min_min_speed = 0
        
class CruiseControl(object):
    def __init__(self):
        self.state = 0
        self.button_long_press_previous_state = 0
        self.button_press_previous_state = 0
        self.throttle_value = 0

class Vars(object):
    def __init__(self):
        self.vesc_fault_code = 0
        self.vesc_temperature_x10 = 0
        self.motor_temperature_x10 = 0
        self.battery_voltage_x10 = 0
        self.battery_current_x100 = 0
        self.motor_current_x100 = 0
        self.motor_power = 0
        self.motor_temperature_sensor_x10 = 0
        self.brakes_are_active = True
        self.torque_weight_x10 = 0
        self.cadence = 0
        self.pedal_human_power = 0
        self.ramp_current_last_time = float(time.monotonic_ns())
        self.ramp_speed_last_time = self.ramp_current_last_time
        self.motor_target_current = 0.0
        self.motor_target_current_regen = 0.0
        self.battery_target_current = 0.0
        self.battery_target_current_regen = 0.0
        self.motor_target_speed = 0.0
        self.assist_level = 0
        self.throttle_value = 0
        self.brakes_value = 0
        self.motor_enable_state = False
        self.button_power_state = 0
        
        self.cruise_control = CruiseControl()
        
        

