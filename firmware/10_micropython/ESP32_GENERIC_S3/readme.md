Tested on ESP32-S3 Zero WaveShare board: https://www.waveshare.com/wiki/ESP32-S3-Zero

This MicroPython were built with MicroPython v1.26.1 sources and with added CAN TWAI driver (folder patch_can_twai).

Flash the MicroPython:

python3 esptool.py erase_flash
python3 esptool.py write_flash 0 ./micropython_v1.26.1_can_twai.bin


