class ESPNowComms(object):
    def __init__(self, espnow, system_data):
        self._espnow = espnow
        self._packets = []
        self._system_data = system_data
        self.power_switch_id = 4 # power switch ESPNow messages ID
        
    def process_data(self):    
        data = None
        try:
            # read a package and discard others available
            while self._espnow:
                rx_data = self._espnow.read()
                if rx_data is None:
                    break
                else:
                    data = rx_data

            # process the package, if available
            if data is not None:
                data = [n for n in data.msg.split()]
                # only process packages for us
                if int(data[0]) == self.power_switch_id:
                    self._system_data.display_communication_counter = int(data[1])
                    self._system_data.turn_off_relay = True if int(data[2]) != 0 else False

        except Exception as ex:
            print(ex)
            pass

    def send_data(self):
        pass