import board
import busio
from digitalio import DigitalInOut
from adafruit_mcp2515 import MCP2515 as CAN
import struct

class torque_sensor(object):

    def __init__(self):
        """Torque sensor"""
        self.cs = DigitalInOut(board.P0_20)
        self.cs.switch_to_output()
        self.spi = busio.SPI(board.P0_17, board.P0_15, board.P0_13)
        self.can_bus = CAN(self.spi, self.cs, baudrate=250000, xtal_frequency=8000000)

    def read(self):
        """Read the torque sensor
        return: torque, cadence
        """
        with self.can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive_and_clean_all_previous()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque[0], cadence[0]
            else:
                return None, None
