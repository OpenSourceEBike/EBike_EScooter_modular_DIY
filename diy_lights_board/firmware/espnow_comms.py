import wifi
import espnow

class ESPNowComms(object):
    def __init__(self, mac_address, message_id):
        
        wifi.radio.enabled = True
        wifi.radio.mac_address = bytearray(mac_address)
        self._message_id = message_id
        self._espnow = espnow.ESPNow()
        
    def get_data(self):
        received_data = None

        try:
            data = self._espnow.read()
            if data is not None:
                data = [n for n in data.msg.split()]
                # only process packages for us
                if int(data[0]) == self._message_id:
                    received_data = int(data[1])

        except Exception as ex:
                pass
        
        return received_data

    def send_data(self):
        pass