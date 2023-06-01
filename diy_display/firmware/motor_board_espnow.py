import espnow as ESPNow

class MotorBoard(object):
    def __init__(self, espnow, mac_address, system_data):
        self._motor_board_espnow = espnow
        peer = ESPNow.Peer(mac=bytes(mac_address), channel=0)
        self._motor_board_espnow.peers.append(peer)

        self._packets = []
        self._system_data = system_data
        self.motor_board_espnow_id = 1
        
    def process_data(self):
        # let's clear the buffer and read last package
        data = self._motor_board_espnow.read()
        while data != None:
            data = self._motor_board_espnow.read()

        if data is not None:
            data = [int(n) for n in data.msg.split()]
            self._system_data.battery_voltage_x10 = int(data[0])
            self._system_data.battery_current_x100 = int(data[1]) * -1.0
            self._system_data.motor_current_x100 = int(data[2]) * -1.0
            self._system_data.motor_speed_erpm = int(data[3])

    def send_data(self):
        try:
            self._motor_board_espnow.send(f"{self.motor_board_espnow_id} {self._system_data.system_power_state}")

        except Exception as exception:
            print(exception)