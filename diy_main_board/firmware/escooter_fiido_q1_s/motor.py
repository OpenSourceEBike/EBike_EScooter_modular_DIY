import vesc

class Motor(object):
    def __init__(self, vesc, dual_motor, motor_1_dual_factor = 0, motor_2_dual_factor = 0, can_id = None):
        self._vesc = vesc
        self._dual_motor = dual_motor
        self.motor_1_dual_factor = motor_1_dual_factor
        self.motor_2_dual_factor = motor_2_dual_factor
        self._can_id = can_id
            
    def set_motor_current_limit_max(self, value):
        self._vesc.set_motor_current_limit_max(value * self.motor_1_dual_factor)
        if self._dual_motor:
            self._vesc.set_can_motor_current_limit_max(value * self.motor_2_dual_factor, self._can_id)
            
    def set_motor_current_limit_min(self, value):
        self._vesc.set_motor_current_limit_min(value * self.motor_1_dual_factor)
        if self._dual_motor:
            self._vesc.set_can_motor_current_limit_min(value * self.motor_2_dual_factor, self._can_id)
            
    def set_battery_current_limit_max(self, value):
        self._vesc.set_battery_current_limit_max(value * self.motor_1_dual_factor)
        if self._dual_motor:
            self._vesc.set_can_battery_current_limit_max(value * self.motor_2_dual_factor, self._can_id)
            
    def set_battery_current_limit_min(self, value):
        self._vesc.set_battery_current_limit_min(value * self.motor_1_dual_factor) 
        if self._dual_motor:
            self._vesc.set_can_battery_current_limit_min(value * self.motor_2_dual_factor, self._can_id)
            
    def set_motor_current_amps(self, value):
        self._vesc.set_motor_current_amps(value * self.motor_1_dual_factor)
        if self._dual_motor:
            self._vesc.set_can_motor_current_amps(value * self.motor_2_dual_factor, self._can_id)
            
    def set_motor_current_brake_amps(self, value):
        self._vesc.set_motor_current_brake_amps(value * self.motor_1_dual_factor)
        if self._dual_motor:
            self._vesc.set_can_motor_current_brake_amps(value * self.motor_2_dual_factor, self._can_id)
            
    def set_motor_limit_speed(self, value):
        self._vesc.set_motor_limit_speed(value)
        if self._dual_motor:
            self._vesc.set_can_motor_limit_speed(value, self._can_id)
            
    def set_motor_speed_rpm(self, value):
        self._vesc.set_motor_speed_rpm(value)
        if self._dual_motor:
            self._vesc.set_can_motor_speed_rpm(value, self._can_id)