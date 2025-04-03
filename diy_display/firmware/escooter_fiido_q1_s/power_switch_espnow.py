import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class PowerSwitch(object):

    def __init__(self, _espnow, mac_address, system_data):
        self._system_data = system_data
        self._espnow = _espnow
        self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)

    def update(self):
        if self._espnow is not None:
            try:
                # add peer before sending the message
                self._espnow.peers.append(self._peer)

                self._espnow.send(f"{int(BoardsIds.POWER_SWITCH)} {int(self._system_data.display_communication_counter)} {int(self._system_data.turn_off_relay)}")

                # now remove the peer
                self._espnow.peers.remove(self._peer)
            except:
                pass
