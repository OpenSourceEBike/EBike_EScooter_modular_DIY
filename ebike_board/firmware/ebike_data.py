import time

class EBike(object):

    def __init__(self):
        self.vesc_fault_code = 0
        self.vesc_temperature_x10 = 0
        self.battery_voltage = 0
        self.battery_current = 0
        self.motor_current = 0
        self.motor_power = 0
        self.motor_speed_erpm = 0
        self.motor_temperature_sensor_x10 = 0
        self.previous_motor_current_target = True
        self.brakes_are_active = True
        self.torque_weight_x10 = 0
        self.cadence = 0
        self.pedal_human_power = 0
        self.ramp_last_time = time.monotonic_ns()
        self.motor_current_target = 0
        self.assist_level = 0