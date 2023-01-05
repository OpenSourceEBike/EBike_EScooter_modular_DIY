#############################
# This firmware will test the messages received on CAN from the torque sensor.
# If no CAN messages are received, at least the "running..." messaged will be printed on console.
# If can message from torque sensor is received, the torque, cadence and other data will be printed on console.

# Set bellow the CAN_TX_PIN and CAN_RX_PIN, depending on the connections you did to your ESP32 board

# NOTE: make sure the Bafang torque sensor has 5V power supply, because it needs at least like 4.7 vols, otherwise it will not work.

#############################

import board
import canio
import time
from canio import Message
import struct

# make sure you set here the correct pins you did connect to your ESP32 board
CAN_TX_PIN = board.IO4
CAN_RX_PIN = board.IO5

# Bafang torque sensor CAN baudrate is 250khz, so use 250000
CAN_BAUDRATE = 250000

can = canio.CAN(CAN_TX_PIN, CAN_RX_PIN, baudrate = CAN_BAUDRATE, loopback=True)

while True:
    with can.listen(timeout=1.0) as listener:
        print(" ")
        message_count = listener.in_waiting()
        print(f"CAN messages available: {message_count}")
        
        for _i in range(message_count):
            msg = listener.receive()
            print(f"Message from: {hex(msg.id)}")

            if isinstance(msg, Message):
                print(f"Message data:", "::".join(["0x{:02X}".format(i) for i in msg.data]))

                torque = struct.unpack_from('<H', msg.data, 0)[0]
                print(f"Torque raw value: {torque}")
                cadence = msg.data[2]
                print(f"Cadence: {cadence}")

    time.sleep(1)
