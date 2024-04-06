import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class Display(object):
    """Display"""

    def __init__(self, display_mac_address, system_data):
        self._system_data = system_data
        self._espnow = ESPNow.ESPNow()
        peer = ESPNow.Peer(mac=bytes(display_mac_address), channel=1)
        self._espnow.peers.append(peer)

    def process_data(self):
        try:
            data = None
            
            # read a package and discard others available
            while self._espnow is not None:
                rx_data_string = self._espnow.read()
                if rx_data_string is None:
                    break
                else:
                    data = rx_data_string
            
            # process the package, if available
            if data is not None:
                data_list = [int(n) for n in data.msg.split()]
                
                # only process packages for us
                # must have 3 elements: message_id + 2 variables                    
                if int(data_list[0]) == int(BoardsIds.MAIN_BOARD) and len(data_list) == 3:
                    self._system_data.motor_enable_state = True if data_list[1] != 0 else False
                    self._system_data.button_power_state = data_list[2]
        except:
            pass

    def update(self):
        if self._espnow is not None:
            try:
                brakes_are_active = 1 if self._system_data.brakes_are_active else 0
                self._espnow.send(f"{int(BoardsIds.DISPLAY)} {int(self._system_data.battery_voltage_x10)} {int(self._system_data.battery_current_x100)} {int(self._system_data.motor_current_x100)} {int(self._system_data.wheel_speed * 10)} {int(brakes_are_active)} {int(self._system_data.vesc_temperature_x10)} {int(self._system_data.motor_temperature_x10)}")
            except:
                pass
