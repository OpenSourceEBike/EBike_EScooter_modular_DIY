import espnow as ESPNow
import supervisor

class Display(object):
    """Display"""

    def __init__(self, display_mac_address, system_data):
        self._system_data = system_data
        self.my_espnow_id = 1

        self._espnow = ESPNow.ESPNow()
        peer = ESPNow.Peer(mac=bytes(display_mac_address), channel=1)
        self._espnow.peers.append(peer)

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
                # only process packages for us
                if int(data[0]) == self.my_espnow_id:
                    self._system_data.motor_enable_state = True if int(data[1]) != 0 else False
        except:
            supervisor.reload()

    def update(self):
        try:
            brakes_are_active = 1 if self._system_data.brakes_are_active else 0
            self._espnow.send(f"{int(self._system_data.battery_voltage_x10)} {int(self._system_data.battery_current_x100)} {int(self._system_data.motor_current_x100)} {self._system_data.motor_speed_erpm} {brakes_are_active}")
        except:
            supervisor.reload()
