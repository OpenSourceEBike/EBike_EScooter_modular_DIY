# Tested with CircuitPython 9.2.9 on ESP32-S3 Zero WaveShare board.

import time
import board
import canio

BAUDRATE = 125000
TX_PIN = board.IO5
RX_PIN = board.IO6

can_bus = canio.CAN(tx=TX_PIN, rx=RX_PIN, baudrate=BAUDRATE)

print("📡 listening for CAN messages..\n")

while True:
    with can_bus.listen(timeout=0.2) as listener:
        while listener.in_waiting():                
            message = listener.receive()
            print(message.id, message.data)
        
    time.sleep(1)

