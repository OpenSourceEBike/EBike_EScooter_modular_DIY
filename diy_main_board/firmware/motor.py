class Motor(object):
    def __init__(self, vesc, motor_cfg):
        self.__vesc = vesc
        self.__motor_cfg = motor_cfg
            
    def set_motor_current_limit_max(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_current_limit_max(value)
        else:
            self.__vesc.set_can_motor_current_limit_max(value)
   
    def set_motor_current_limit_min(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_current_limit_min(value)
        else:
            self.__vesc.set_can_motor_current_limit_min(value)
            
    def set_battery_current_limit_max(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_battery_current_limit_max(value)
        else:
            self.__vesc.set_can_battery_current_limit_max(value)
            
    def set_battery_current_limit_min(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_battery_current_limit_min(value)
        else:
            self.__vesc.set_can_battery_current_limit_min(value)
            
    def set_motor_current_amps(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_current_amps(value)
        else:
            self.__vesc.set_can_motor_current_amps(value)
            
    def set_motor_current_brake_amps(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_current_brake_amps(value)
        else:
            self.__vesc.set_can_motor_current_brake_amps(value)
            
    def set_motor_limit_speed(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_limit_speed(value)
        else:
            self.__vesc.set_can_motor_limit_speed(value)
            
    def set_motor_speed_rpm(self, value):
        if self.__motor_cfg.motor_number == 0:
            self.__vesc.set_motor_speed_rpm(value)
        else:
            self.__vesc.set_can_motor_speed_rpm(value)
            
class MotorData(object):
     def __init__(self):           
        self.motor_target_current_limit_max = 0
        self.motor_target_current_limit_min = 0
        self.battery_target_current_limit_max = 0
        self.battery_target_current_limit_min = 0
        self.motor_erpm_max_speed_limit = 0
        self.motor_max_speed_limit = 0
        self.motor_min_current_start = 0
        self.motor_max_current_regen = 0
        self.battery_max_current_regen = 0
        self.motor_speed_erpm = 0