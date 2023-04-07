import busio
import struct

class M365_dashboard(object):
    """M365_dashboard"""

    def __init__(self, uart_tx_pin, uart_rx_pin, ebike_data):
        """M365 dashboard
        :param ~microcontroller.Pin uart_tx_pin: UART TX pin that connects to UART half duplex
        :param ~microcontroller.Pin uart_tx_pin: UART RX pin that connects to UART half duplex
        :param ~EBikeAppData ebike_app_data: Ebike app data object
        """
        self._ebike_data = ebike_data

        # configure UART
        self._uart = busio.UART(
            uart_tx_pin,
            uart_rx_pin,
            baudrate = 115200,
            timeout = 0.005, # 5ms is enough for reading the UART
            receiver_buffer_size = 132) # seems Xiaomi M365 dashboard messages are no more than 132
        
        # init variables
        self._rx_package = RXPackage()
        self._read_and_unpack__state = 0
        self._read_and_unpack__len = 0
        self._read_and_unpack__cnt = 0

    # read and process UART data
    def process_data(self):
        """Receive and process periodically data.
        Can be called fast but probably no point to do it faster than 10ms"""
        self._read_and_unpack()
        self._process_data()

    def _crc(self, data):
        crc = 0
        for byte in data:
            crc += byte

        crc ^= 0xFFFF
        return crc
            
    def _read_and_unpack(self):
        # only read next data bytes after we process the previous package
        if self._rx_package.received == False:
            rx_array = self._uart.read()
            if rx_array is not None:
                for data in rx_array:
                    # find start byte 1
                    if self._read_and_unpack__state == 0:
                        if (data == 0x55):
                            self._rx_package.data[0] = data
                            self._read_and_unpack__state = 1
                        else:
                            self._read_and_unpack__state = 0

                    # find start byte 2
                    elif self._read_and_unpack__state == 1:
                        if (data == 0xAA):
                            self._rx_package.data[1] = data
                            self._read_and_unpack__state = 2
                        else:
                            self._read_and_unpack__state = 0

                    # len byte
                    elif self._read_and_unpack__state == 2:
                        self._rx_package.data[2] = data
                        self._read_and_unpack__len = data + 6
                        self._read_and_unpack__state = 3

                    # rest of the package
                    elif self._read_and_unpack__state == 3:
                        self._rx_package.data[self._read_and_unpack__cnt  + 3] = data
                        self._read_and_unpack__cnt += 1

                        # end of the package
                        if self._read_and_unpack__cnt >= self._read_and_unpack__len:

                            # calculate the CRC
                            crc = self._crc(self._rx_package.data[2: self._read_and_unpack__len - 2])
                            # get the original CRC
                            crc_original = self._rx_package.data[self._read_and_unpack__len - 2] + (self._rx_package.data[self._read_and_unpack__len - 1] << 8)
                            
                            # check if CRC is ok                    
                            self._rx_package.received = True if crc == crc_original else False

                            self._read_and_unpack__cnt = 0
                            self._read_and_unpack__state = 0
                            self._uart.reset_input_buffer()
                            break
                        
    def _process_data(self):
        if self._rx_package.received == True:
            
            command = self._rx_package.data[4]
            if command == 0x65:
                self._ebike_data.throttle_value = self._rx_package.data[7]
                self._ebike_data.brakes_value = self._rx_package.data[8]

            self._rx_package.received = False

class RXPackage():
    data = bytearray(255)
    received = False
