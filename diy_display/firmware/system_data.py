import time

class SystemData(object):

    def __init__(self):
        self.vesc_fault_code = 0
        self.battery_voltage_x10 = 0
        self.battery_current_x100 = 0
        self.motor_power = 0
        self.motor_current_x100 = 0
        self.wheel_speed_x10 = 0
        self.brakes_are_active = False
        self.torque_weight = 0
        self.cadence = 0
        self.ramp_last_time = time.monotonic_ns()
        self.motor_current_target = 0
        self.assist_level = 0
        self.vesc_temperature_x10 = 0
        self.motor_temperature_x10 = 0    
        self.display_communication_counter = 0
        self.turn_off_relay = False
        self.motor_enable_state = False
        self.lights_state = False
        self.rear_lights_board_pins_state = 0
        self.front_lights_board_pins_state = 0
        self.buttons_state = 0x0101 # this value 
