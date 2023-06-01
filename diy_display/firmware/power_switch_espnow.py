import espnow as ESPNow

class PowerSwitch(object):

    def __init__(self, espnow, mac_address, system_data):
        self._system_data = system_data
        self.power_switch_id = 5 # power switch ESPNow messages ID

        self._espnow = espnow
        peer = ESPNow.Peer(mac=bytes(mac_address), channel=0)
        self._espnow.peers.append(peer)
        
    def update(self):
        try:
            self._espnow.send(f"{self.power_switch_id} {int(self._system_data.display_communication_counter)} {int(self._system_data.turn_off_relay)}")
            self._system_data.turn_off_relay = False

        except Exception as exception:
            print(exception)
