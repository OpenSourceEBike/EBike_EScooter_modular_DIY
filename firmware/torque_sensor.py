import board
import busio
from digitalio import DigitalInOut
from adafruit_mcp2515 import MCP2515 as CAN
import struct

class torque_sensor(object):

    def __init__(self):
        """Torque sensor"""
        self.cs = DigitalInOut(board.P0_24)
        self.cs.switch_to_output()
        self.spi = busio.SPI(board.P0_17, board.P0_15, board.P0_13)
        self.can_bus = CAN(self.spi, self.cs, baudrate=250000, xtal_frequency=8000000)

    def read(self):
        """Read the torque sensor
        return: torque, cadence
        """
        with self.can_bus.listen(timeout=1.0) as listener:
            if (listener.in_waiting()):
                msg = listener.receive_and_clean()

                # unpack values from the byte array
                torque = struct.unpack_from('>H', msg.data, 0) # 2 bytes
                cadence = struct.unpack_from('>c', msg.data, 2) # 1 byte

                print(msg)

                return torque, cadence
            else:
                return None, None