import time

class EBike(object):

    def __init__(self):
        self.battery_voltage = 0
        self.battery_current = 0
        self.motor_current = 0
        self.motor_speed_erpm = 0
        self.previous_motor_current_target = True
        self.brakes_are_active = True
        self.torque_weight = 0
        self.cadence = 0
        self.ramp_last_time = time.monotonic_ns()
        self.motor_current_target = 0
        self.brakes_counter = 0