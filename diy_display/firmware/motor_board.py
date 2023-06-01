import espnow

class MotorBoard(object):
    def __init__(self, system_data):
        pass
        
        # self._motor_board_espnow = espnow.ESPNow()
        # self._packets = []
        # self._system_data = system_data
        
    def process_data(self):
        pass
        # # let's clear the buffer and read last package
        # data = self._motor_board_espnow.read()
        # while data != None:
        #     data = self._motor_board_espnow.read()

        # if data is not None:
        #     data = [int(n) for n in data.msg.split()]
        #     self._system_data.battery_voltage_x10 = int(data[0])
        #     self._system_data.battery_current_x100 = int(data[1]) * -1.0
        #     self._system_data.motor_current_x100 = int(data[2]) * -1.0
        #     self._system_data.motor_speed_erpm = int(data[3])

    def send_data(self):
        pass