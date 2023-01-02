import busio
import time
from digitalio import DigitalInOut
from adafruit_mcp2515 import MCP2515 as CAN
import struct

class TorqueSensor(object):

    def __init__(self, cs, clock, mosi, miso, cadence_timeout = 1.0):
        """Torque sensor
        :param ~microcontroller.Pin CS: the pin to use for the chip select.
        :param ~microcontroller.Pin clock: the pin to use for the clock.
        :param ~microcontroller.Pin MOSI: the Main Out Selected In pin.
        :param ~microcontroller.Pin MISO: the Main In Selected Out pin.
        :param float cadence_timeout: timeout in seconds, to reset cadence value if no new value higher than 0 is read
        """
        self._cs = DigitalInOut(cs)
        self._cs.switch_to_output()
        self._spi = busio.SPI(clock, mosi, miso)
        self._can_bus = CAN(self._spi, self._cs, baudrate=250000, xtal_frequency=8000000)
        self.cadence_timeout = cadence_timeout
        self.cadence_previous_time = 0
        self.cadence_previous = 0
        self.cadence = 0
        self.torque_weight = 0

    @property
    def value_raw(self):
        """Torque sensor raw values
        return: torque, cadence and progressive_byte
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive_and_clean_all_previous()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value
                progressive_byte = msg.data[3] # last byte should be a value that increases on each package

                return torque[0], cadence[0], progressive_byte
            else:
                return None, None

    @property
    def value(self):
        """Torque sensor value
        return: torque, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive_and_clean_all_previous()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque[0], cadence[0]
            else:
                return None, None

    @property
    def weight_value(self):
        """Torque sensor weight value
        return: torque weight, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive_and_clean_all_previous()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                torque = (torque[0] - 750) / 61 # convert to kgs
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque, cadence[0]
            else:
                return None, None
              
    @property
    def weight_value_cadence_filtered(self):
        """Torque sensor weight value with cadence filtered
        return: torque weight, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            
            msg = bytearray()
            cadence = None
            torque = None
            now = time.monotonic()
            counter = 0

            while True:
                if listener.in_waiting():
                    msg = listener.receive()

                    cadence = struct.unpack_from('<B', msg.data, 2)[0] # 1 byte: cadence value
                    if cadence > 0:
                        # we got a new cadence value
                        self.cadence_previous_time = now
                        self.cadence_previous = cadence

                        torque = struct.unpack_from('<H', msg.data, 0)[0] # 2 bytes: torque value
                        torque = (torque - 750) / 61 # convert to kgs

                        # ignore previous messages, just clean them
                        listener.clean_existing_messages()

                        return torque, cadence
                    
                    else:
                       # cadence is 0
                      
                       counter += 1
                       # check if previous 5 messages are always 0, if so, stop here
                       if counter > 5:
                           # check for cadence timeout
                           timeout = True if now > (self.cadence_previous_time + self.cadence_timeout) else False
                           if timeout:
                               self.cadence_previous = 0
                               self.cadence_previous_time = now
                           else:
                               # keep cadence with previous value
                               cadence = self.cadence_previous

                           torque = struct.unpack_from('<H', msg.data, 0)[0] # 2 bytes: torque value
                           torque = (torque - 750) / 61 # convert to kgs
                         
                           # ignore previous messages, just clean them
                           listener.clean_existing_messages()

                           return torque, cadence
                          
                else:
                    # check for cadence timeout
                    timeout = True if now > (self.cadence_previous_time + self.cadence_timeout) else False
                    if cadence == 0:
                        # we got cadence = 0
                        if timeout:
                            self.cadence_previous = 0
                            self.cadence_previous_time = now
                        else:
                            # keep cadence with previous value
                            cadence = self.cadence_previous

                        torque = struct.unpack_from('<H', msg.data, 0)[0] # 2 bytes: torque value
                        torque = (torque - 750) / 61 # convert to kgs

                    else:
                        # we got no new values from torque sensor
                        if timeout:
                            self.cadence_previous = 0
                            self.cadence_previous_time = now
                        else:
                            cadence = self.cadence_previous

                    return torque, cadence