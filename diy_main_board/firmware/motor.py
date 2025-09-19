import time
import canio
import struct

class Motor(object):
    _can = None
    _tx_4 = bytearray(4)
    _tx_8 = bytearray(8)

    def __init__(self, data):
        self.data = data
        
        # configure CAN for communications with VESC
        # Vesc is kind of a Singleton
        if self.data.cfg.can_tx_pin is not None and \
            self.data.cfg.can_rx_pin is not None:
            Motor._can = canio.CAN(tx=self.data.cfg.can_tx_pin, rx=self.data.cfg.can_rx_pin, baudrate=125000)

    def _pack_and_send(self, buf, command):
        if Motor._can is None:
            raise RuntimeError("CAN not initialized.")
        
        message = canio.Message(id=(self.data.cfg.can_id | command << 8), data=buf, extended=True)
        Motor._can.send(message)
        time.sleep(0.0025)  # tiny yield (~2.5 ms) to let CircuitPython run background tasks
                     # (USB, GC, CAN RX) and avoid missed frames / TX lockups

    def update_motor_data(self, motor_1, motor_2=None):
                
        with Motor._can.listen(timeout=0.2) as listener:
            while listener.in_waiting():                
                message = listener.receive()
                message_id = (message.id >> 8) & 0xFF
                can_id = message.id & 0xFF
                
                if can_id == motor_1.data.cfg.can_id:
                    motor_data = motor_1.data
                elif motor_2 is not None and \
                    can_id == motor_2.data.cfg.can_id:
                    motor_data = motor_2.data
                else:
                    continue
                                
                 # CAN_PACKET_STATUS_1
                if message_id == 9:
                    motor_data.speed_erpm = struct.unpack_from('>l', message.data, 0)[0]
                    motor_data.motor_current_x100 = struct.unpack_from('>h', message.data, 4)[0]
                        
                # CAN_PACKET_STATUS_4
                elif message_id == 16:
                    motor_data.vesc_temperature_x10 = struct.unpack_from('>h', message.data, 0)[0]
                    motor_data.motor_temperature_x10 = struct.unpack_from('>h', message.data, 2)[0]
                    motor_data.battery_current_x100 = struct.unpack_from('>h', message.data, 4)[0]
                    
                # CAN_PACKET_STATUS_5
                elif message_id == 27:
                    motor_data.battery_voltage_x10 = struct.unpack_from('>h', message.data, 4)[0]
                
                # CAN_PACKET_STATUS_7
                elif message_id == 99:
                    motor_data.battery_soc_x1000 = struct.unpack_from('>h', message.data, 0)[0]

    def set_motor_current_amps(self, value):
        """Set motor target current in Amps"""
        value = value * 1000 # current in mA
        
        struct.pack_into('>l', Motor._tx_4, 0, int(value))
        self._pack_and_send(Motor._tx_4, 1) # CAN_PACKET_SET_CURRENT = 1
        
    def set_motor_current_brake_amps(self, value):
        """Set motor current brake / regen Amps"""
        value = value * 1000 # current in mA
        
        struct.pack_into('>l', Motor._tx_4, 0, int(value))
        self._pack_and_send(Motor._tx_4, 2) # CAN_PACKET_SET_CURRENT_BRAKE = 2
            
    def set_motor_speed_rpm(self, value):
        """Set motor speed in RPM"""
        struct.pack_into('>l', Motor._tx_4, 0, int(value))
        self._pack_and_send(Motor._tx_4, 3) # CAN_PACKET_SET_RPM = 3
                
    def set_motor_current_limits(self, min, max):
        """Set motor current limits in Amps"""
        min = min * 1000 # current in mA
        max = max * 1000 # current in mA
        
        struct.pack_into('>l', Motor._tx_8, 0, int(min))
        struct.pack_into('>l', Motor._tx_8, 4, int(max))
        self._pack_and_send(Motor._tx_8, 21) # CAN_PACKET_SET_CURRENT_LIMITS = 21    
            
    def set_battery_current_limits(self, min, max):
        """Set battery current limis in Amps"""
        min = min * 1000 # current in mA
        max = max * 1000 # current in mA
        
        struct.pack_into('>l', Motor._tx_8, 0, int(min))
        struct.pack_into('>l', Motor._tx_8, 4, int(max))
        self._pack_and_send(Motor._tx_8, 23) # CAN_PACKET_SET_BATTERY_CURRENT_LIMITS = 23 

    def motor_get_can_state(self):
        return (
            Motor._can.state,
            Motor._can.receive_error_count,
            Motor._can.transmit_error_count,
        )

class MotorData:
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