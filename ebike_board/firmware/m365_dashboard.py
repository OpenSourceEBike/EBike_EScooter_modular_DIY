import busio
import simpleio
import thisbutton as tb

class M365_dashboard(object):
    """M365_dashboard"""

    def __init__(self, uart_tx_pin, uart_rx_pin, button_pin, ebike_data):
        """M365 dashboard
        :param ~microcontroller.Pin uart_tx_pin: UART TX pin that connects to UART half duplex
        :param ~microcontroller.Pin uart_tx_pin: UART RX pin that connects to UART half duplex
        :param ~microcontroller.Pin button_pin: dashboard button pin
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
        
        # button
        self._button = tb.thisButton(button_pin, True)
        self._button.assignClick(self._button_click_callback)
        self._button.assignLongPressStart(self._button_long_click_callback)
        
        # init variables
        self._beep_state = False
        self._rx_package = RXPackage()
        self._read_and_unpack__state = 0
        self._read_and_unpack__len = 0
        self._read_and_unpack__cnt = 0
        
        self._tx_buffer = bytearray(96)
        self._tx_buffer[0] = 0x55
        self._tx_buffer[1] = 0xAA

    def _button_click_callback(self):
        self._beep_state = True
        self._ebike_data.update_data_to_dashboard = True

    def _button_long_click_callback(self):
        self._beep_state = True
        self._ebike_data.update_data_to_dashboard = True

    # read and process UART data
    def process_data(self):
        """Receive and process periodically data.
        Can be called fast but probably no point to do it faster than 10ms"""
        self._read_and_unpack()
        self._process_data()
        
        self._button.tick()

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
                            break
                        
    def _process_data(self):
        if self._rx_package.received == True:
            self._rx_package.received = False
            
            command = self._rx_package.data[4]
            if command == 0x65: # reveive throttle and brake
                self._ebike_data.throttle_value = self._rx_package.data[7]
                self._ebike_data.brakes_value = self._rx_package.data[8]
                
                # If we got a throttle and brake package, that have high priority, we can now ignore all other
                # possible packages on the buffer. But if update_data_to_dashboard is needed, then do not ignore
                # other packages on the buffer, in the hope the asking update_data_to_dashboard is there
                if not self._ebike_data.update_data_to_dashboard:
                    self._uart.reset_input_buffer()

            elif command == 0x64 and self._ebike_data.update_data_to_dashboard: # ask to send data to dashboard
                self._ebike_data.update_data_to_dashboard = False

                self._tx_buffer[2] = 0x08 # message lenght
                self._tx_buffer[3] = 0x21 # receiver
                self._tx_buffer[4] = command # command
                self._tx_buffer[5] = 0x00 # ??
                self._tx_buffer[6] = 0 # mode
                
                # battery SOC
                self._tx_buffer[7] = int(simpleio.map_range(self._ebike_data.battery_voltage, 33, 42, 0, 96))

                self._tx_buffer[8] = 0x00 # light: 0x00 - off, 0x40 - on

                # check to seed if a beep need to be sent
                if self._beep_state:
                    beep = 1
                    self._beep_state = False
                else:
                    beep = 0
                    
                self._tx_buffer[9] = beep # beep

                self._tx_buffer[10] = self._ebike_data.wheel_speed # wheel_speed
                self._tx_buffer[11] = 0 # error code

                crc = self._crc(self._tx_buffer[2: 12])
                self._tx_buffer[12] = crc & 0xFF
                self._tx_buffer[13] = (crc >> 8) & 0xFF
                self._tx_buffer[14] = 0 # '\0'
                self._uart.write(self._tx_buffer) # transmit the package

class RXPackage():
    data = bytearray(255)
    received = False
