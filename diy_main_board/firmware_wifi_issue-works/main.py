import time
import board
import neopixel

pixels = neopixel.NeoPixel(board.NEOPIXEL, 8, brightness=0.01, auto_write=True)

GREEN = (0, 255, 0)

while True:
  pixels.fill(GREEN)
  time.sleep(0.25)
  pixels.fill((0,0,0))
  time.sleep(0.25)