import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class PowerSwitch(object):

    def __init__(self, _espnow, mac_address, system_data):
        self._espnow = _espnow
        self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
        self._espnow.peers.append(self._peer)
        self._system_data = system_data

    def send_data(self):
        if self._espnow is not None:
            try:
                self._espnow.send(
                    f"{int(BoardsIds.POWER_SWITCH)} \
                    {int(self._system_data.display_communication_counter)} \
                    {int(self._system_data.turn_off_relay)}",
                    self._peer)
                
            except Exception as e:
                print(f"PowerSwitch tx error: {e}")
