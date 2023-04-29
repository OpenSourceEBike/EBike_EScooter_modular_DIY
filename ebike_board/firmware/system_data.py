import time

class SystemData(object):

    def __init__(self):
        self.vesc_fault_code = 0
        self.vesc_temperature_x10 = 0
        self.battery_voltage = 0
        self.battery_current = 0
        self.motor_current = 0
        self.motor_power = 0
        self.motor_speed_erpm = 0
        self.motor_temperature_sensor_x10 = 0
        self.previous_motor_target = True
        self.brakes_are_active = True
        self.torque_weight_x10 = 0
        self.cadence = 0
        self.pedal_human_power = 0
        self.ramp_last_time = time.monotonic_ns()
        self.motor_target = 0
        self.assist_level = 0
        self.throttle_value = 0
        self.brakes_value = 0
        self.wheel_speed = 0
        self.update_data_to_dashboard = False
