from time import sleep
import board
import busio
from digitalio import DigitalInOut
from adafruit_mcp2515 import MCP2515 as CAN

cs = DigitalInOut(board.P0_24)
cs.switch_to_output()
spi = busio.SPI(board.P0_17, board.P0_15, board.P0_13)
can_bus = CAN(spi, cs)

while True:

    with can_bus.listen(timeout=1.0) as listener:

        message_count = listener.in_waiting()
        for _i in range(message_count):
            msg = listener.receive()
            print("Message from ", hex(msg.id))
            message_str = "::".join(["0x{:02X}".format(i) for i in msg.data])
            print("Message: " + message_str)
            print(" ")

    sleep(1)