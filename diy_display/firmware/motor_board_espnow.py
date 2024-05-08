import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class MotorBoard(object):
    def __init__(self, _espnow, mac_address, system_data):
        self._espnow = _espnow
        self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
        self._system_data = system_data
        
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
                # must have 8 elements: message_id + 7 variables
                if data_list[0] == int(BoardsIds.DISPLAY) and len(data_list) == 8:
                    self._system_data.battery_voltage_x10 = data_list[1]
                    self._system_data.battery_current_x100 = data_list[2]
                    self._system_data.motor_current_x100 = data_list[3]
                    self._system_data.wheel_speed_x10 = data_list[4]
                    self._system_data.brakes_are_active = True if data_list[5] == 1 else False
                    self._system_data.vesc_temperature_x10 = data_list[6]
                    self._system_data.motor_temperature_x10 = data_list[7]
                    
        except:
            pass

    def send_data(self):
        if self._espnow is not None:
            try:
                # add peer before sending the message
                self._espnow.peers.append(self._peer)

                motor_enable_state = 1 if self._system_data.motor_enable_state else 0
                self._espnow.send(f"{int(BoardsIds.MAIN_BOARD)} {motor_enable_state} {self._system_data.button_power_state}")

                # now remove the peer
                self._espnow.peers.remove(self._peer)
            except:
                pass
