# boot.py — ESP32 MicroPython
# Hold BOOT (GPIO0) within 1s after reset to enter safe mode

import machine
import time

BOOT_PIN = 0          # ESP32 BOOT button is GPIO0
CHECK_TIME_MS = 1000  # 1 second window

btn = machine.Pin(BOOT_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

start = time.ticks_ms()
safe = False

while time.ticks_diff(time.ticks_ms(), start) < CHECK_TIME_MS:
    if btn.value() == 0:   # BOOT pressed (active low)
        safe = True
        break
    time.sleep_ms(10)

if safe:
    print("SAFE MODE: BOOT button pressed")
    raise SystemExit   # skips main.py, REPL stays active
