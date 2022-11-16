import board
import busio
from digitalio import DigitalInOut
from adafruit_mcp2515.canio import Message, RemoteTransmissionRequest
from adafruit_mcp2515 import MCP2515 as CAN

class VESC(object):

    def __init__(self):
        self.cs = DigitalInOut(board.P0_24)
        self.cs.switch_to_output()
        self.spi = busio.SPI(board.P0_17, board.P0_15, board.P0_13)

        self.can_bus = CAN(
            self.spi, self.cs, loopback=True, silent=True
        )  # use loopback to test without another device

    def enter(self, machine):
        pass

    def exit(self, machine):
        pass

    def update(self, machine):
        if switch.fell:
            machine.paused_state = machine.state.name
            machine.pause()
            return False
        return True