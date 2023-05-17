import espnow

class MotorBoard(object):
    def __init__(self, system_data):
        
        self._motor_board_espnow = espnow.ESPNow()
        self._packets = []
        self._system_data = system_data
        
    def process_data(self):
        # let's clear the buffer
        data = None
        while(len(self._motor_board_espnow)):
            data = self._motor_board_espnow.read()

        if data is not None:
            data = [int(n) for n in data.msg.split()]
            self._system_data.battery_voltage_x10 = data[0]
            self._system_data.battery_current_x100 = data[1]
            self._system_data.motor_speed_erpm = data[2]

    def send_data(self):
        pass