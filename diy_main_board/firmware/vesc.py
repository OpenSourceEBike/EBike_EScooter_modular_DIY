import busio
import canio
import struct
import time

# Singleton class as can only exist one object to communicate with VESC
class Vesc(object):

    def __init__(self, front_motor_data, rear_motor_data):
        
        self._front_motor_data = front_motor_data
        self._rear_motor_data = rear_motor_data
        
        self._counter_messages = 0

        # configure UART for communications with VESC
        if self._rear_motor_data.cfg.uart_tx_pin is not None and \
            self._rear_motor_data.cfg.uart_rx_pin is not None:
            self._uart = busio.UART(
                rear_motor_data.cfg.uart_tx_pin,
                rear_motor_data.cfg.uart_rx_pin,
                baudrate = rear_motor_data.cfg.uart_baudrate,
                timeout = 0.005, # 5ms is enough for reading the UART
                # NOTE: on CircuitPyhton 8.1.0-beta.2, a value of 512 will make the board to reboot if wifi wireless workflow is not connected
                receiver_buffer_size = 1024) # VESC PACKET_MAX_PL_LEN = 512
        else:
            self._can_bus = canio.CAN(rear_motor_data.cfg.can_tx_pin, rear_motor_data.cfg.can_tx_pin, baudrate = 500000)
        
        # assuming max packet size of 79, like the one to read motor data
        self._vesc_data = bytearray(79 * 2)

    # code taken from:
    # https://gist.github.com/oysstu/68072c44c02879a2abf94ef350d1c7c6
    def _crc16(self, data):
        '''
        CRC-16 (CCITT) implemented with a precomputed lookup table
        '''
        table = [ 
            0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7, 0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
            0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6, 0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
            0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485, 0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
            0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4, 0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
            0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823, 0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
            0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12, 0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
            0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41, 0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
            0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70, 0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
            0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F, 0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
            0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E, 0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
            0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D, 0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
            0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C, 0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
            0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB, 0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
            0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A, 0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
            0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9, 0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
            0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8, 0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0
        ]
        
        crc = 0
        for byte in data:
            crc = (crc << 8) ^ table[(crc >> 8) ^ byte]
            crc &= 0xFFFF                                   # important, crc must stay 16bits all the way through

        return crc
    
    def _process_response_GET_VALUES_SETUP_SELECTIVE(self, response):
        # Check for the controler ID on the message, to figure out of
        # which motor the data belongs to       
        controller_can_id = response[58]
        if controller_can_id == 0:
            motor_data = self._rear_motor_data
        else:
            motor_data = self._front_motor_data
            
        motor_data.battery_soc_x1000 = struct.unpack_from('>h', response, 27)[0]
        motor_data.controller_can_id = response[58]
    
    def _process_response_GET_VALUES(self, response):
        # Check for the controler ID on the message, to figure out of
        # which motor the data belongs to
        controller_can_id = response[60]
        if controller_can_id == 0:
            motor_data = self._rear_motor_data
        else:
            motor_data = self._front_motor_data
        
        # store the motor controller data
        motor_data.vesc_temperature_x10 = struct.unpack_from('>h', response, 3)[0]
        motor_data.motor_temperature_x10 = struct.unpack_from('>h', response, 5)[0]
        motor_data.motor_current_x100 = struct.unpack_from('>l', response, 7)[0]
        motor_data.battery_current_x100 = struct.unpack_from('>l', response, 11)[0]
        motor_data.speed_erpm = struct.unpack_from('>l', response, 25)[0]
        motor_data.battery_voltage_x10 = struct.unpack_from('>h', response, 29)[0]
        motor_data.vesc_fault_code = response[55]
       
    def _can_pack_and_send(self, buf, can_id, command):      
        # send packet to CAN
        message = canio.Message(id=(can_id | command << 8), data=buf, extended=True)
        print(message.id, [b for b in message.data])
        self._can_bus.send(message)

    def _uart_pack_and_send(self, buf, response_len, delay):
        start_byte = 2
        end_byte = 3
                
        # if command is COMM_FORWARD_CAN, then get the real command
        vesc_command = buf[0]
        if vesc_command == 34: # COMM_FORWARD_CAN
            vesc_command = buf[2]

        #start byte + len + data + CRC 16 bits + end byte
        lenght = len(buf)
        package_len = 1 + 1 + lenght + 2 + 1
        crc = self._crc16(buf)

        data_array = bytearray(package_len)
        data_array[0] = start_byte
        data_array[1] = lenght
        data_array[2: 2 + lenght] = buf # copy data
        data_array[package_len - 3] = (crc & 0xff00) >> 8
        data_array[package_len - 2] = crc & 0x00ff
        data_array[package_len - 1] = end_byte
        
        # send packet to UART
        self._uart.write(data_array)
        
        time.sleep(delay)

        bytes_in_uart_buffer = self._uart.in_waiting
        # try to read response only if we expect it
        if response_len > 0 and bytes_in_uart_buffer >= response_len:
            while bytes_in_uart_buffer:
                
                # check for expected start byte 2
                if self._uart.read(1)[0] != start_byte:
                    bytes_in_uart_buffer = self._uart.in_waiting
                    if bytes_in_uart_buffer > 0:
                        # restart the while loop
                        continue
                    else:
                        # exit if there are no more bytes to read
                        return None
                
                # check for expected payload lenght
                payload_len = response_len - 5
                if self._uart.read(1)[0] != payload_len:
                    bytes_in_uart_buffer = self._uart.in_waiting
                    if bytes_in_uart_buffer > 0:
                        continue
                    else:
                        return None
                    
                # check for expected vesc_command
                if self._uart.read(1)[0] != vesc_command:
                    bytes_in_uart_buffer = self._uart.in_waiting
                    if bytes_in_uart_buffer:
                        continue
                    else:
                        return None
                    
                # if the UART buffer has no complete response, discard all buffer and exit
                bytes_in_uart_buffer = self._uart.in_waiting
                if bytes_in_uart_buffer < (response_len - 3):
                    self._uart.reset_input_buffer()
                    return None

                # here we hope we are syncronized and have the full packet
                # insert the initial bytes at the begin
                self._vesc_data[0] = start_byte
                self._vesc_data[1] = payload_len
                self._vesc_data[2] = vesc_command
                self._vesc_data[3:] = self._uart.read(response_len - 3)
                
                # check for expected end byte
                if self._vesc_data[-1] != end_byte:
                    self._uart.reset_input_buffer()
                    return None

                # check for CRC
                crc_calculated = self._crc16(self._vesc_data[2:-3])
                crc = (self._vesc_data[-3] * 256) + self._vesc_data[-2]
                if crc != crc_calculated:
                    self._uart.reset_input_buffer()
                    return None

                self._uart.reset_input_buffer()
                return self._vesc_data
        else:
            return None
    
    def update_can_motor_data(self):
        counter_messages = 8
        with self._can_bus.listen(timeout=1.0) as listener: 
            # Read max of 8 messages at a time
            # 4 messages for each motor / VESC 
            while listener.in_waiting() and counter_messages > 0:
                msg = listener.receive()
                counter_messages -= 1
                
                from_can_id = msg.id & 0xFF
                if from_can_id == 0:
                        motor_data = self._rear_motor_data
                if from_can_id == 1:
                        motor_data = self._front_motor_data
                
                can_message_id = (msg.id >> 8) & 0xFF
                
                 # CAN_PACKET_STATUS_1
                if can_message_id == 9:
                    motor_data.speed_erpm = struct.unpack_from('>l', msg.data, 0)[0]
                    motor_data.motor_current_x100 = struct.unpack_from('>h', msg.data, 4)[0]
                        
                # CAN_PACKET_STATUS_4
                # DONE
                elif can_message_id == 16:
                    motor_data.vesc_temperature_x10 = struct.unpack_from('>h', msg.data, 0)[0]
                    motor_data.motor_temperature_x10 = struct.unpack_from('>h', msg.data, 2)[0]
                    motor_data.battery_current_x100 = struct.unpack_from('>h', msg.data, 4)[0]
                    
                # CAN_PACKET_STATUS_5
                elif can_message_id == 27:
                    motor_data.battery_voltage_x10 = struct.unpack_from('>h', msg.data, 4)[0]
                
                # CAN_PACKET_STATUS_7
                elif can_message_id == 99:
                    motor_data.battery_soc_x1000 = struct.unpack_from('>h', msg.data, 0)[0]
            
            # ignore other messages in the buffer
            while listener.in_waiting():
                listener.receive()

    def update_uart_battery_soc(self):
        tx_command_buffer = bytearray(5)
        tx_command_buffer[0] = 47 # COMM_GET_VALUES_SETUP = 47   
        response = self._uart_pack_and_send(tx_command_buffer, 75, 0.01)
            
        if response is not None:        
            self._process_response_GET_VALUES_SETUP_SELECTIVE(response)
            
    def update_uart_motor_data(self):
        
        tx_command_buffer = bytearray(1)
        tx_command_buffer[0] = 4 # COMM_GET_VALUES = 4; 79 bytes response (firmware bldc main branch, April 2024, commit: c8be115bb5be5a5558e3a50ba82e55931e3a45c4)
        response = self._uart_pack_and_send(tx_command_buffer, 79, 0.01)
            
        if response is not None:            
            self._process_response_GET_VALUES(response)
        
    def update_uart_can_motor_data(self):
        
        tx_command_buffer = bytearray(3)
        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id
        tx_command_buffer[2] = 4 # COMM_GET_VALUES = 4; 79 bytes response (firmware bldc main branch, April 2024, commit: c8be115bb5be5a5558e3a50ba82e55931e3a45c4)
        response = self._uart_pack_and_send(tx_command_buffer, 79, 0.02)

        if response is not None:
            self._process_response_GET_VALUES(response)
    
    def set_can_motor_current_amps(self, value, can_id):
        """Set battery Amps"""
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(4)
        struct.pack_into('>l', tx_command_buffer, 0, int(value))
        self._can_pack_and_send(tx_command_buffer, can_id, 1) # CAN_PACKET_SET_CURRENT = 1
      
    def set_uart_motor_current_amps(self, value):
        """Set battery Amps"""
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(5)
        tx_command_buffer[0] = 6 # COMM_SET_CURRENT = 6; no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_motor_current_amps(self, value):
        """Set battery Amps"""
        value = value * 1000 # current in mA
                
        tx_command_buffer = bytearray(7)
        
        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id
        
        tx_command_buffer[2] = 6 # COMM_SET_CURRENT = 6; no response
        
        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_can_motor_current_brake_amps(self, value, can_id):
        """Set battery brake / regen Amps"""
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(4)
        struct.pack_into('>l', tx_command_buffer, 0, int(value))
        self._can_pack_and_send(tx_command_buffer, can_id, 2) # CAN_PACKET_SET_CURRENT_BRAKE = 2
        
    def set_uart_motor_current_brake_amps(self, value):
        """Set battery brake / regen Amps"""
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(5)
        tx_command_buffer[0] = 7 # COMM_SET_CURRENT_BRAKE = 7; no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_motor_current_brake_amps(self, value):
        """Set battery brake / regen Amps for CAN bus"""
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(7)
        
        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id
        
        tx_command_buffer[2] = 7 # COMM_SET_CURRENT_BRAKE = 7; no response
        
        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_can_motor_speed_rpm(self, value, can_id):
        """Set motor speed in RPM"""
        tx_command_buffer = bytearray(4)
        struct.pack_into('>l', tx_command_buffer, 0, int(value))
        self._can_pack_and_send(tx_command_buffer, can_id, 3) # CAN_PACKET_SET_RPM = 3
           
    def set_uart_motor_speed_rpm(self, value):
        """Set motor speed in RPM"""
        tx_command_buffer = bytearray(5)
        tx_command_buffer[0] = 8 # COMM_SET_RPM = 8; no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_motor_speed_rpm(self, value):
        tx_command_buffer = bytearray(7)
        
        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id
        
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[2] = 8 # COMM_SET_RPM = 8; no response
        
        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_can_motor_current_limits(self, min, max, can_id):
        min = min * 1000 # current in mA
        max = max * 1000 # current in mA
        
        tx_command_buffer = bytearray(8)
        struct.pack_into('>l', tx_command_buffer, 0, int(min))
        struct.pack_into('>l', tx_command_buffer, 4, int(max))
        self._can_pack_and_send(tx_command_buffer, can_id, 21) # CAN_PACKET_SET_CURRENT_LIMITS = 21    
        
    def set_uart_motor_current_limit_min(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(5)
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[0] = 200 # no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_motor_current_limit_min(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(7)
        
        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id
        
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[2] = 200 # no response
        
        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_motor_current_limit_max(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(5)
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[0] = 201 # no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_motor_current_limit_max(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(7)

        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id

        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[2] = 201 # no response

        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
            
    def set_can_battery_current_limits(self, min, max, can_id):
        min = min * 1000 # current in mA
        max = max * 1000 # current in mA
        
        tx_command_buffer = bytearray(8)
        struct.pack_into('>l', tx_command_buffer, 0, int(min))
        struct.pack_into('>l', tx_command_buffer, 4, int(max))
        self._can_pack_and_send(tx_command_buffer, can_id, 23) # CAN_PACKET_SET_BATTERY_CURRENT_LIMITS = 23   
        
    def set_uart_battery_current_limit_min(self, value):
        value = value * 1000 # current in mA

        tx_command_buffer = bytearray(5)
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[0] = 202 # no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
    
    def set_uart_can_battery_current_limit_min(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(7)

        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id

        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[2] = 202 # no response

        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)

    def set_uart_battery_current_limit_max(self, value):
        value = value * 1000 # current in mA

        tx_command_buffer = bytearray(5)
        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[0] = 203 # no response
        struct.pack_into('>l', tx_command_buffer, 1, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)
        
    def set_uart_can_battery_current_limit_max(self, value):
        value = value * 1000 # current in mA
        
        tx_command_buffer = bytearray(7)

        tx_command_buffer[0] = 34 # COMM_FORWARD_CAN
        tx_command_buffer[1] = self._front_motor_data.cfg.can_id

        # VESC custom tx_command_buffer on custom firmware
        tx_command_buffer[2] = 203 # no response

        struct.pack_into('>l', tx_command_buffer, 3, int(value))
        self._uart_pack_and_send(tx_command_buffer, 0, 0.001)

