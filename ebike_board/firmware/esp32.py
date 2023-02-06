import microcontroller

class ESP32(object):

    @property
    def temperature_x10(self):
        return int(microcontroller.cpu.temperature * 10)