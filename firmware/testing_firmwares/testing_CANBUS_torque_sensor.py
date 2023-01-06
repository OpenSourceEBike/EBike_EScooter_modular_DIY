#############################
# This firmware will test the messages received on CAN from the torque sensor.
# If no CAN messages are received, at least the "running..." messaged will be printed on console.
# If can message from torque sensor is received, the torque, cadence and other data will be printed on console.

# Set bellow the CAN_TX_PIN and CAN_RX_PIN, depending on the connections you did to your ESP32 board

#############################

import board
import canio
import time

# make sure you set here the correct pins you did connect to your ESP32 board
CAN_TX_PIN = board.IO4
CAN_RX_PIN = board.IO5

# Bafang torque sensor CAN baudrate is 250khz, so use 250000
CAN_BAUDRATE = 250000

can = canio.CAN(CAN_TX_PIN, CAN_RX_PIN, baudrate = CAN_BAUDRATE)

while True:
    with can.listen(timeout = 1.0) as listener:
        print(" ")

        message_count = listener.in_waiting()
        print("CAN messages available:", message_count)
        
        while message_count > 0:
            message_count = message_count - 1

            can_message = listener.receive()
            print("Message from ID:", hex(can_message.id)) # torque sensor ID is: 0x1f83100

            torque = (can_message.data[1] * 256) + can_message.data[0]
            print("Torque raw value:", torque)

            cadence = can_message.data[2]
            print("Cadence:", cadence)

    time.sleep(1)
