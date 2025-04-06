import espnow as ESPNow

# firmware_common/boards_ids.py should be placed on the root path
from firmware_common.boards_ids import BoardsIds

class Display(object):
    """Display"""

    def __init__(self, vars, motor_data, mac_address):
        self._espnow = ESPNow.ESPNow()
        self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
        self._espnow.peers.append(self._peer)
        self._vars = vars
        self._motor_data = motor_data

    def process_data(self):
        try:
            data = None
            
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
                # must have 4 elements: message_id + 3 variables                    
                if int(data_list[0]) == int(BoardsIds.MAIN_BOARD) and len(data_list) == 4:
                    self._vars.motors_enable_state = True if data_list[1] != 0 else False
                    self._vars.buttons_state = data_list[2]
                    self._vars.assist_level = data_list[3]
        
        except Exception as e:
            print(f"Display rx error: {e}")

    def send_data(self):
        if self._espnow is not None:
            try:
                brakes_are_active = 1 if self._vars.brakes_are_active else 0            
                battery_current_x100 = int(self._motor_data.battery_current_x100)
                motor_current_x100 = int(self._motor_data.motor_current_x100)
                
                # Send the max value only
                vesc_temperature_x10 = self._motor_data.vesc_temperature_x10
                motor_temperature_x10 = self._motor_data.motor_temperature_x10
                
                # Assuming battery voltage and wheel speed are the same for both motors
                self._espnow.send(
                    f"{int(BoardsIds.DISPLAY)} \
                    {int(self._motor_data.battery_voltage_x10)} \
                    {battery_current_x100} {motor_current_x100} \
                    {int(self._motor_data.wheel_speed * 10)} \
                    {int(brakes_are_active)} \
                    {int(vesc_temperature_x10)} \
                    {int(motor_temperature_x10)}",
                    self._peer)
            
            except Exception as e:
                print(f"Display tx error: {e}")
