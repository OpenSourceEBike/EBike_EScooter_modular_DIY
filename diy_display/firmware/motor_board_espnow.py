import espnow as ESPNow
import supervisor

class MotorBoard(object):
    def __init__(self, _espnow, mac_address, system_data):
        self._espnow = _espnow
        self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
        self._espnow.peers.append(self._peer)

        self._packets = []
        self._system_data = system_data
        self.message_id = 1 # motor board ESPNow messages ID
        
    def process_data(self):
        try:
            data = None
            data_temp = None

            # read a package and discard others available
            while True:
                data_temp = self._espnow.read()
                if data_temp is None:
                    break
                else:
                    data = data_temp
            
            # process the package
            if data is not None:
                data = [n for n in data.msg.split()]
                self._system_data.battery_voltage_x10 = int(data[0])
                self._system_data.battery_current_x100 = int(data[1]) * -1.0
                self._system_data.motor_current_x100 = int(data[2]) * -1.0
                self._system_data.motor_speed_erpm = int(data[3])
                self._system_data.brakes_are_active = True if int(data[4]) == 1 else False
        except:
            pass

    def send_data(self):
        try:
            motor_enable_state = 1 if self._system_data.motor_enable_state else 0
            self._espnow.send(f"{int(self.message_id)} {motor_enable_state}")
        except:
            # this should not happen, as the motor board should exist and ready to receive ESPNow communication
            # but if for some reason this fails, reset the display
            supervisor.reload()

    def get_peer(self):
        return self._peer