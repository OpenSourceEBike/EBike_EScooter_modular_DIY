import espnow as ESPNow

class MotorBoard(object):
    def __init__(self, _espnow, mac_address, system_data):
        self._motor_board_espnow = _espnow
        peer = ESPNow.Peer(mac=bytes(mac_address), channel=0)
        self._motor_board_espnow.peers.append(peer)

        self._packets = []
        self._system_data = system_data
        self.motor_board_espnow_id = 1
        
    def process_data(self):
        # let's read last package
        data = self._motor_board_espnow.read()

        if data is not None:
            data = [n for n in data.msg.split()]
            self._system_data.battery_voltage_x10 = int(data[0])
            self._system_data.battery_current_x100 = int(data[1]) * -1.0
            self._system_data.motor_current_x100 = int(data[2]) * -1.0
            self._system_data.motor_speed_erpm = int(data[3])
            self._system_data.brakes_are_active = True if int(data[4]) == 1 else False
            print(data)

    def send_data(self):
        try:
            system_power_state = 1 if self._system_data.system_power_state else 0
            self._motor_board_espnow.send(f"{int(self.motor_board_espnow_id)} {system_power_state}")
            print("ok tx motor board")
        except:
            pass