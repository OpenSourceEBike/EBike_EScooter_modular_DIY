import vesc

class Motor(object):
    def __init__(self, vesc, dual_motor):
        self.__vesc = vesc
        self.__dual_motor = dual_motor
            
    def set_motor_current_limit_max(self, value):
        self.__vesc.set_motor_current_limit_max(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_current_limit_max(value)
            
    def set_motor_current_limit_min(self, value):
        self.__vesc.set_motor_current_limit_min(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_current_limit_min(value)
            
    def set_battery_current_limit_max(self, value):
        self.__vesc.set_battery_current_limit_max(value)
        if self.__dual_motor:
            self.__vesc.set_can_battery_current_limit_max(value)
            
    def set_battery_current_limit_min(self, value):
        self.__vesc.set_battery_current_limit_min(value) 
        if self.__dual_motor:
            self.__vesc.set_can_battery_current_limit_min(value)
            
    def set_motor_current_amps(self, value):
        self.__vesc.set_motor_current_amps(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_current_amps(value)
            
    def set_motor_current_brake_amps(self, value):
        self.__vesc.set_motor_current_brake_amps(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_current_brake_amps(value)
            
    def set_motor_limit_speed(self, value):
        self.__vesc.set_motor_limit_speed(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_limit_speed(value)
            
    def set_motor_speed_rpm(self, value):
        self.__vesc.set_motor_speed_rpm(value)
        if self.__dual_motor:
            self.__vesc.set_can_motor_speed_rpm(value)