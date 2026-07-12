import espnow as ESPNow
from common import config_runtime as cfg
from common.espnow_protocol import BOARD_DISPLAY, BOARD_MOTOR

DEBUG = bool(getattr(cfg, "espnow_debug", False))

class Display(object):
  """Display"""

  def __init__(self, vars, motor_data, mac_address):
    self._espnow = ESPNow.ESPNow()
    self._peer = ESPNow.Peer(mac=bytes(mac_address), channel=1)
    self._espnow.peers.append(self._peer)
    self._vars = vars
    self._motor_data = motor_data
    self._rx_error_active = False
    self._tx_error_active = False

  def receive_process_data(self):
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
        if int(data_list[0]) == BOARD_MOTOR and len(data_list) == 4:
          self._vars.motors_enable_state = True if data_list[1] != 0 else False
          self._vars.buttons_state = data_list[2]
          self._vars.assist_level = data_list[3]
      self._rx_error_active = False
    
    except Exception as e:
      if not self._rx_error_active:
        if DEBUG:
          print(f"Display rx error: {e}")
      self._rx_error_active = True

  def send_data(self):
    if self._espnow is not None:
      try:
        brakes_are_active = 1 if self._vars.brakes_are_active else 0            
        battery_current_x10 = int(self._motor_data.battery_current_x10)
        motor_current_x10 = int(self._motor_data.motor_current_x10)
        
        # Send the max value only
        vesc_temperature_x10 = self._motor_data.vesc_temperature_x10
        motor_temperature_x10 = self._motor_data.motor_temperature_x10
        
        # Assuming battery voltage and wheel speed are the same for both motors
        self._espnow.send(
                    f"{BOARD_DISPLAY} \
          {int(self._motor_data.battery_voltage_x10)} \
          {battery_current_x10} \
          {int(self._rear_motor_data.battery_soc_x1000)} \
          {int(self._motor_data.wheel_speed * 10)} \
          {int(brakes_are_active)} \
          {int(vesc_temperature_x10)} \
          {int(motor_temperature_x10)}",
          self._peer)
        self._tx_error_active = False
      
      except Exception as e:
        if not self._tx_error_active:
          if DEBUG:
            print(f"Display tx error: {e}")
        self._tx_error_active = True
