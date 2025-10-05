Tested on ESP32-S3 Zero WaveShare board: https://www.waveshare.com/wiki/ESP32-S3-Zero

This MicroPython were built with MicroPython v1.26.1 sources and with added CAN TWAI driver (folder patch_can_twai).

Flash the MicroPython:

esptool.py --chip esp32s3 -p /dev/ttyACM0 -b 460800 --before=default_reset --after=hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 4MB 0x0 ./bootloader.bin 0x10000 ./micropython.bin 0x8000 ./partition-table.bin

