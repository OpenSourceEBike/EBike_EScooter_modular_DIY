import espnow as ESPNow

class Logger(object):

    def __init__(self, mac_address, system_data):
        self._system_data = system_data
        self.message_id = 99 # logger board ESPNow message ID

        self._espnow = ESPNow.ESPNow()
        peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
        self._espnow.peers.append(peer)

    def update(self):
        try:
            brakes_are_active = 1 if self._system_data.brakes_are_active else 0
            self._espnow.send(f"{self.message_id} {int(self._system_data.battery_voltage_x10)} {int(self._system_data.battery_current_x100)} {int(self._system_data.motor_current_x100)} {self._system_data.motor_speed_erpm} {brakes_are_active}")
        except:
            pass
