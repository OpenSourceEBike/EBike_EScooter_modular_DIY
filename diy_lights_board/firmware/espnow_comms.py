import wifi
import espnow
from .main import lights_board, FRONT_VERSION, REAR_VERSION
from ...firmware_common.boards_ids import BoardsIds

class ESPNowComms(object):
    def __init__(self, mac_address):
        
        wifi.radio.enabled = True
        wifi.radio.mac_address = bytearray(mac_address)
        self._espnow = espnow.ESPNow()
        self._board_id = 0

        if lights_board == FRONT_VERSION:
            self._board_id = BoardsIds.FRONT_LIGHTS
        elif lights_board == REAR_VERSION:
            self._board_id = BoardsIds.REAR_LIGHTS
        
        
    def get_data(self):    
        received_data = None
        data = None
        try:
            # read a package and discard others available
            while self._espnow is not None:
                rx_data = self._espnow.read()
                if rx_data is None:
                    break
                else:
                    data = rx_data

            # process the package, if available
            if data is not None:
                data_list = [int(n) for n in data.msg.split()]

                # only process packages for us                
                # must have 2 elements: message_id + 1 variables
                if data_list[0] == int(self._board_id) and len(data_list) == 2:
                    received_data = data[1]

        except Exception as ex:
            print(ex)
        
        return received_data

    def send_data(self):
        pass