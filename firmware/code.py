"""CircuitPython Essentials UART Serial example"""
import board
import busio
import digitalio
import time

# For most CircuitPython boards:
led = digitalio.DigitalInOut(board.LED1)
led.direction = digitalio.Direction.OUTPUT

uart = busio.UART(board.P0_24, board.P0_22, baudrate=9600)

value = 0

while True:
    value += 1
    buf = bytearray([value])

    print(buf)
    uart.write(buf)

    led.value = True
    time.sleep(0.5)
    led.value = False
    time.sleep(0.5)
