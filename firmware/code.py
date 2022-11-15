import board
import digitalio
from digitalio import Pull
import analogio
import busio
import time

# configure NRF52840 board green LED
led = digitalio.DigitalInOut(board.LED1)
led.direction = digitalio.Direction.OUTPUT

# configure UART for communications with VESC
uart_vesc = busio.UART(board.P0_20, board.P0_22, baudrate = 115200)

# configure UART for communications with display
uart_display = busio.UART(board.P0_09, board.P0_10, baudrate = 19200)

# configure ADC input for throttle signal
adc_throttle = analogio.AnalogIn(board.P0_29)

# configure IO input for brake sensor signal
io_brake_sensor = digitalio.DigitalInOut(board.P0_02)
io_brake_sensor.pull = Pull.UP
io_brake_sensor.direction = digitalio.Direction.INPUT

# configure IO input for wheel speed sensor signal
io_wheelspeed_sensor = digitalio.DigitalInOut(board.P1_15)
io_wheelspeed_sensor.pull = Pull.UP
io_wheelspeed_sensor.direction = digitalio.Direction.INPUT

value = 0

while True:
    value += 1
    buf = bytearray([value])

    print("UARTs values: " + str(value))
    uart_vesc.write(buf)
    uart_display.write(buf)

    print("ADC throttle: " + str(adc_throttle.value))
    print("IO brake sensor: " + str(io_brake_sensor.value))
    print("IO wheelspeed sensor: " + str(io_wheelspeed_sensor.value))
    print(" ")

    led.value = True
    time.sleep(0.5)
    led.value = False
    time.sleep(0.5)
