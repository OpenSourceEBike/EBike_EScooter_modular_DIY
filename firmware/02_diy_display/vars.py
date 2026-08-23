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
    self.rear_speed_telemetry_valid = False
    self.battery_soc_x1000 = -1 # -1 means value is invalid
    self.bms_battery_current_x100 = None
    # Timestamp of the BASIC BMS frame that supplied the current above.  This
    # lets charging detection reject a regeneration sample captured before the
    # scooter came to a stop.
    self.bms_battery_current_last_update_ms = 0
    self.battery_is_charging = False
    # Passive battery DC-resistance history. Timestamps are local RTC epoch
    # seconds, or zero when no valid RTC is available.
    self.battery_resistance_last_mohm = None
    self.battery_resistance_last_timestamp = 0
    self.battery_resistance_min_mohm = None
    self.battery_resistance_min_timestamp = 0
    self.battery_resistance_max_mohm = None
    self.battery_resistance_max_timestamp = 0
    self.battery_resistance_history_dirty = False
    # Shutdown persistence transaction state. The row flag prevents a retry
    # from appending twice after history succeeded but summary publication did
    # not. A recovered summary is repaired at the next explicit shutdown.
    self.battery_resistance_history_row_saved = False
    self.battery_resistance_summary_repair_pending = False
    # Prevent repeated motor status frames from duplicating alert/history state.
    self.battery_resistance_received_this_boot = False
    # One-shot (resistance_mohm, duration_ms) consumed by MainScreen.
    self.battery_resistance_alert_pending = None
    self.battery_resistance_enabled = True
    self.battery_resistance_measurement_available = True
    self.battery_resistance_config_error = ''
    self.battery_resistance_debug_phase = -1
    self.battery_resistance_debug_boot_seconds = 0
    self.battery_resistance_debug_error_count = 0
    self.battery_resistance_debug_sample_count = 0
    self.battery_resistance_debug_reference_sample_count = 0
    self.battery_resistance_debug_phase_elapsed_seconds = 0
    self.lisp_motion_loss_count = 0
    self.lisp_thermal_loss_count = 0
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
    self.lights_switch_state = False
    self.auto_lights_state = False
    self.lights_board_pins_state = 0
    self.motor_board_rx_ok = False
    self.motor_board_tx_ok = False
    self.motor_lights_tx_ok = False
    self.lights_board_comm_ok = False
    self.power_switch_board_comm_ok = False
    self.motor_board_tx_last_ok_ms = 0
    self.motor_board_rx_last_ok_ms = 0
    self.lights_board_tx_last_ok_ms = 0
    self.buttons_state = 0
    # Latched button events avoid losing a click between the 50 ms button
    # poller and the slower UI task.
    self.power_click_pending = False
    self.power_long_click_pending = False
    self.shutdown_request = False
    self.buttons = None
    self.rtc = None
    self.time_string = ''
    self.rtc_time_valid = False
    self.rtc_ntp_sync_valid = False
    # Wi-Fi/NTP sync is scheduled once per confirmed charging session.
    self.rtc_sync_pending = False
    self.rtc_sync_started = False
    # This is set before scheduling the sync, so a brief loss of BMS current
    # after the radio handover cannot re-enter CHARGING and start it again.
    # It is reset only after a confirmed end of the charging session.
    self.rtc_sync_done_for_charging_session = False
    self.charging_reconfirm_pending = False
    self.charging_reconfirm_started_ms = 0
    self.charging_reconfirm_failed = False
    # Result of the latest charging-screen Wi-Fi/NTP synchronization.
    # Values used by the screen: idle, pending, success, fallback, failed.
    self.rtc_sync_result = 'idle'
    self.comms_paused = False
