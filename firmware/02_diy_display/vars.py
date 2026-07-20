# vars.py  — MicroPython version of Vars

import time

def _ticks_ns():
  """Return nanosecond-resolution monotonic time, fallback to us*1000 if needed."""
  try:
    return time.ticks_ns()
  except AttributeError:
    return time.ticks_us() * 1000

class Vars:
  def __init__(self):
    self.vesc_fault_code = 0
    self.battery_voltage_x10 = 0
    self.battery_current_x10 = 0
    self.battery_soc_x1000 = -1 # -1 means value is invalid
    self.bms_battery_current_x100 = None
    self.battery_is_charging = False
    self.motor_power_percent = 0
    self.motor_current_x10 = 0
    self.wheel_speed_x10 = 0
    self.brakes_are_active = False
    self.regen_braking_is_active = False
    self.cruise_control_is_active = False
    self.throttle_is_active = False
    self.motor_throttle_rearm_required = False
    self.throttle_right_fault = False
    self.throttle_left_fault = False
    self.torque_weight = 0
    self.cadence = 0
    self.mode = 0
    self.ramp_last_time = _ticks_ns()
    self.motor_current_target = 0
    self.assist_level = 0
    self.rear_vesc_temperature_x10 = 0
    self.front_vesc_temperature_x10 = 0
    self.rear_motor_temperature_x10 = 0
    self.front_motor_temperature_x10 = 0
    self.turn_off_relay = False
    self.motor_enable_state = False
    self.lights_state = False
    self.auto_lights_state = False
    self.lights_board_pins_state = 0
    self.motor_board_rx_ok = False
    self.motor_board_tx_ok = False
    self.motor_lights_tx_ok = False
    self.lights_board_comm_ok = False
    self.power_switch_board_comm_ok = False
    self.motor_board_tx_last_ok_ms = 0
    self.motor_board_rx_last_ok_ms = 0
    self.buttons_state = 0
    self.shutdown_request = False
    self.buttons = None
    self.rtc = None
    self.time_string = ''
    self.rtc_time_valid = False
    self.rtc_ntp_sync_valid = False
    # Wi-Fi/NTP sync is scheduled on each charging entry.
    self.rtc_sync_pending = False
    self.rtc_sync_started = False
    # Result of the latest charging-screen Wi-Fi/NTP synchronization.
    # Values used by the screen: idle, pending, success, fallback, failed.
    self.rtc_sync_result = 'idle'
    self.comms_paused = False
