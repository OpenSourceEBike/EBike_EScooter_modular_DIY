import busio
import struct

class Vesc(object):
    """VESC"""

    def __init__(self, uart_tx_pin, uart_rx_pin, app_data):
        """VESC
        :param ~microcontroller.Pin uart_tx_pin: UART TX pin that connects to VESC
        :param ~microcontroller.Pin uart_tx_pin: UART RX pin that connects to VESC
        :param ~EBikeAppData ebike_app_data: Ebike app data object
        """
        self._app_data = app_data

        # configure UART for communications with VESC
        self._uart = busio.UART(
            uart_tx_pin,
            uart_rx_pin,
            baudrate = 115200, # VESC UART baudrate
            timeout = 0.005, # 5ms is enough for reading the UART
            receiver_buffer_size = 512) # VESC PACKET_MAX_PL_LEN = 512

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

    def _pack_and_send(self, buf, response_len):

        #start byte + len + data + CRC 16 bits + end byte
        lenght = len(buf)
        package_len = 1 + 1 + lenght + 2 + 1
        crc = self._crc16(buf)

        data_array = bytearray(package_len)
        data_array[0] = 2 # start byte
        data_array[1] = lenght
        data_array[2: 2 + lenght] = buf # copy data
        data_array[package_len - 3] = (crc & 0xff00) >> 8
        data_array[package_len - 2] = crc & 0x00ff
        data_array[package_len - 1] = 3

        # send packet to UART
        self._uart.write(data_array)
        
        # try to read response only if we expect it
        if response_len is not 0:
            data = self._uart.read(response_len)  # read up to response_len bytes
            return data
        else:
            return None
            
    def refresh_data(self):
        """Read VESC motor data and update vesc_motor_data"""
        # COMM_GET_VALUES = 4; 79 bytes response
        command = bytearray([4])
        response = self._pack_and_send(command, 79)

        if response is not None:
            # print(",".join(["{}".format(i) for i in response]))
            # for index, data in enumerate(response):
            #     print(str(index) + ": " + str(data))

            # store the motor controller data
            self._app_data.vesc_temperature_x10 = struct.unpack_from('>h', response, 3)[0] - 110 # # found experimentaly that this value has a positive offset of 11 degrees - 2023.01.27
            self._app_data.motor_current = struct.unpack_from('>l', response, 7)[0] / 100.0
            self._app_data.battery_current = struct.unpack_from('>l', response, 11)[0] / 100.0
            self._app_data.motor_speed_erpm = struct.unpack_from('>l', response, 25)[0]
            self._app_data.battery_voltage = struct.unpack_from('>h', response, 29)[0] / 10.0
            self._app_data.vesc_fault_code = response[55]
            print(self._app_data.battery_voltage)

    def send_heart_beat(self):
        """Send the heart beat / alive command to VESC, must be sent at least every 0.9s or VESC will stop the motor"""
        # COMM_ALIVE = 30; no response
        command = bytearray([30])
        self._pack_and_send(command, 0)

    def set_motor_current_amps(self, value):
        """Set battery Amps"""
        value = value * 1000 # current in mA

        # COMM_SET_CURRENT = 6; no response
        command = bytearray(5)
        command[0] = 6
        struct.pack_into('>l', command, 1, int(value))
        self._pack_and_send(command, 0)
    
    def set_motor_current_brake_amps(self, value):
        """Set battery brake / regen Amps"""
        value = value * 1000 # current in mA

        # COMM_SET_CURRENT_BRAKE = 7; no response
        command = bytearray(5)
        command[0] = 7
        struct.pack_into('>l', command, 1, int(value))
        self._pack_and_send(command, 0)

    def set_motor_speed_erpm(self, value):
        """Set motor speed in ERPM"""
        # COMM_SET_RPM = 8; no response
        command = bytearray(5)
        command[0] = 8
        struct.pack_into('>l', command, 1, int(value))
        self._pack_and_send(command, 0)

    def brake(self):
        """ Brake: will set the motor current to 0 amps, efectivly coasting"""
        # COMM_SET_CURRENT_BRAKE = 7; no response
        command = bytearray(5)
        command[0] = 7
        struct.pack_into('>l', command, 1, 0)

        # send 3x to avoid possibility of VESC missing receiving this command
        self._pack_and_send(command, 0)
        self._pack_and_send(command, 0)
        self._pack_and_send(command, 0)
