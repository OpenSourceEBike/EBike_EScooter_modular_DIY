import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class Display(object):
    """Display"""

    def __init__(self, vars, rear_motor_data, display_mac_address):
        self.__vars = vars
        self.__rear_motor_data = rear_motor_data
        self.__espnow = ESPNow.ESPNow()
        peer = ESPNow.Peer(mac=bytes(display_mac_address), channel=1)
        self.__espnow.peers.append(peer)

    def process_data(self):
        try:
            data = None
            
            # read a package and discard others available
            while self.__espnow is not None:
                rx_data_string = self.__espnow.read()
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
                    self.__vars.motor_enable_state = True if data_list[1] != 0 else False
                    self.__vars.button_power_state = data_list[2]
        except Exception as e:
            print(f"ESPNow display read error: {e}")

    def update(self):
        if self.__espnow is not None:
            try:
                brakes_are_active = 1 if self.__vars.brakes_are_active else 0
                self.__espnow.send(f"{int(BoardsIds.DISPLAY)} {int(self.__vars.battery_voltage_x10)} {int(self.__vars.battery_current_x100)} {int(self.__vars.motor_current_x100)} {int(self.__rear_motor_data.wheel_speed * 10)} {int(brakes_are_active)} {int(self.__vars.vesc_temperature_x10)} {int(self.__vars.motor_temperature_x10)}")
            except Exception as e:
                print(f"ESPNow display send error: {e}")
