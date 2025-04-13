from vesc import Vesc

class Motor(object):
    _front_motor_data = None
    _rear_motor_data = None
    _vesc = None
    
    def __init__(self, motor_data):
        
        self.data = motor_data
        
        if motor_data.cfg.can_id == 1:
            Motor._front_motor_data = motor_data
            
        if motor_data.cfg.can_id == 0:
            Motor._rear_motor_data = motor_data
        
        # Must be dual motor: front and rear motors
        if Motor._front_motor_data is not None and Motor._rear_motor_data is not None:        
            Motor._vesc = Vesc(Motor._front_motor_data, Motor._rear_motor_data)
            
        self._cfg = motor_data.cfg
        
    def _is_can_motor(self):
        return self._cfg.is_can
        
    def update_motor_data(self):
        if self._is_can_motor():
            Motor._vesc.update_can_motor_data()
        else:
            if self._cfg.can_id == 1:
                Motor._vesc.update_uart_can_motor_data()
            else:
                Motor._vesc.update_uart_motor_data()
            
    def set_motor_current_limit_max(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_current_limit_max(value, self._cfg.can_id)
        else:        
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_current_limit_max(value)
            else:
                Motor._vesc.set_uart_motor_current_limit_max(value)
   
    def set_motor_current_limit_min(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_current_limit_min(value, self._cfg.can_id)
        else:        
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_current_limit_min(value)
            else:
                Motor._vesc.set_uart_motor_current_limit_min(value)
            
    def set_battery_current_limit_max(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_battery_current_limit_max(value, self._cfg.can_id)
        else:
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_battery_current_limit_max(value)
            else:
                Motor._vesc.set_uart_battery_current_limit_max(value)
            
    def set_battery_current_limit_min(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_battery_current_limit_min(value, self._cfg.can_id)
        else:
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_battery_current_limit_min(value)
            else:
                Motor._vesc.set_uart_battery_current_limit_min(value)
            
    def set_motor_current_amps(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_current_amps(value, self._cfg.can_id)
        else:                
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_current_amps(value)
            else:
                Motor._vesc.set_uart_motor_current_amps(value)
            
    def set_motor_current_brake_amps(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_current_brake_amps(value, self._cfg.can_id)
        else:        
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_current_brake_amps(value)
            else:
                Motor._vesc.set_uart_motor_current_brake_amps(value)
            
    def set_motor_limit_speed(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_limit_speed(value, self._cfg.can_id)
        else:
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_limit_speed(value)
            else:
                Motor._vesc.set_uart_motor_limit_speed(value)
            
    def set_motor_speed_rpm(self, value):
        if self._is_can_motor():
            Motor._vesc.set_can_motor_limit_speed(value, self._cfg.can_id)
        else:
            if self._cfg.can_id == 1:
                Motor._vesc.set_uart_can_motor_speed_rpm(value)
            else:
                Motor._vesc.set_uart_motor_speed_rpm(value)
            
class MotorData(object):
    def __init__(self, cfg):           
        self.motor_target_current_limit_max = 0
        self.motor_target_current_limit_min = 0
        self.battery_target_current_limit_max = 0
        self.battery_target_current_limit_min = 0
        self.motor_min_current_start = 0
        self.speed_erpm = 0
        self.wheel_speed = 0
        self.motor_target_speed = 0.0
        self.cfg = cfg
        self.vesc_temperature_x10 = 0
        self.motor_temperature_x10 = 0
        self.motor_current_x100 = 0
        self.battery_current_x100 = 0
        self.battery_voltage_x10 = 0
        self.battery_soc_x1000 = 0
        self.vesc_fault_code = 0
        