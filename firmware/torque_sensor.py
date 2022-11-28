import busio
from digitalio import DigitalInOut
from adafruit_mcp2515 import MCP2515 as CAN
import struct

class TorqueSensor(object):

    def __init__(self, cs, clock, mosi, miso):
        """Torque sensor
        :param ~microcontroller.Pin CS: the pin to use for the chip select.
        :param ~microcontroller.Pin clock: the pin to use for the clock.
        :param ~microcontroller.Pin MOSI: the Main Out Selected In pin.
        :param ~microcontroller.Pin MISO: the Main In Selected Out pin.
        """
        self.__cs = DigitalInOut(cs)
        self.__cs.switch_to_output()
        self.__spi = busio.SPI(clock, mosi, miso)
        self.__can_bus = CAN(self.__spi, self.__cs, baudrate=250000, xtal_frequency=8000000)

    @property
    def value(self):
        """Torque sensor value
        return: torque, cadence
        """
        with self.__can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive_and_clean_all_previous()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque[0], cadence[0]
            else:
                return None, None
