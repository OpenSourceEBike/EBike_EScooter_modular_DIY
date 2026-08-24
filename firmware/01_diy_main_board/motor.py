# motor.py — MicroPython (ESP32-S3) TWAI/CAN helper for VESC-style frames
# Driver API assumed:
#   from can import CAN
#   CAN(tx=<gpio>, rx=<gpio>, baudrate=<int>, mode=<int>)
#   can.recv() -> None or (msg_id:int, is_ext:bool, rtr:bool, data:bytes/bytearray)
#   can.send(buf:bytes/bytearray, msg_id:int, extframe:bool=True/False, timeout:int=0)

import time
import struct
from can import CAN

# Common errno values seen across ports/usermods (for resilient TX)
_EAGAIN    = 11
_EBUSY     = 16
_ETIMEDOUT = 110
_ENOTCONN  = 107
_ECONNRST  = 104
_ETXFAIL   = 0x0107


class Motor(object):
  """
  Minimal wrapper around a shared CAN instance, with:
      - fire-and-forget TX (never raises)
      - non-blocking RX drain + VESC packet decoding
      - simple TX health counters
  """
  _can = None                 # shared CAN instance (singleton)
  _tx_4 = bytearray(4)
  _tx_8 = bytearray(8)

  def __init__(self, data):
    self.data = data

    # TX health / observability
    self.tx_ok = 0
    self.tx_drop = 0
    self.last_tx_error = None  # tuple(code, repr)

    # Configure CAN once (singleton). Assume cfg fields exist and are valid.
    if Motor._can is None:
      tx_pin = int(self.data.cfg.can_tx_pin)
      rx_pin = int(self.data.cfg.can_rx_pin)
      baud   = int(self.data.cfg.can_baudrate)
      mode   = int(self.data.cfg.can_mode)  # 0 == NORMAL in this driver

      Motor._can = CAN(
        tx=tx_pin,
        rx=rx_pin,
        baudrate=baud,
        mode=mode
      )
      mode_name = "NORMAL" if mode == 0 else str(mode)
      print("CAN configured:",
                  "rx_pin =", rx_pin, "tx_pin =", tx_pin,
                  "baudrate =", baud, "mode =", mode_name)

  # ------------------ INTERNAL: TX (never raise) ------------------

  def _pack_and_send(self, buf, command) -> bool:
    """
    Fire-and-forget send. Never raises; drops on error.
    Returns True on success, False if dropped.
    """
    if Motor._can is None:
      self.last_tx_error = ("NO_CAN", "CAN not initialized")
      self.tx_drop += 1
      return False

    # VESC-style composing: low 8b = node id, next 8b = command
    msg_id = (int(self.data.cfg.can_id) & 0xFF) | ((int(command) & 0xFF) << 8)

    try:
      # Non-blocking send; extframe=True for VESC extended IDs pattern
      Motor._can.send(buf, msg_id, extframe=True, timeout=0)
      self.tx_ok += 1
      time.sleep_ms(3)  # required delay for reliable ESP32 CAN transmission
      return True

    except OSError as e:
      code = e.args[0] if e.args else None
      self.last_tx_error = (code, repr(e))
      self.tx_drop += 1
      # Known transient/bus-state errors: just drop
      if code in (_EAGAIN, _EBUSY, _ETIMEDOUT, _ENOTCONN, _ECONNRST, _ETXFAIL, None):
        return False
      return False

    except Exception as e:
      self.last_tx_error = ("EXC", repr(e))
      self.tx_drop += 1
      return False

  # ------------------ INTERNAL: RX (non-blocking) ------------------

  @staticmethod
  def _recv_nonblock():
    can = Motor._can
    if not can:
      return None
    try:
      # Non-blocking in this driver: returns None if no frame available
      return can.recv()
    except OSError:
      # Includes ETIMEDOUT when no frame within internal wait window
      return None
    except Exception:
      return None

  @staticmethod
  def _record_sequence(motor_data, sequence, previous_name, loss_name):
    """Count skipped modulo-256 telemetry sequence values, not the first."""
    previous = getattr(motor_data, previous_name)
    if previous is not None:
      delta = (sequence - previous) & 0xff
      if delta > 1:
        setattr(motor_data, loss_name, getattr(motor_data, loss_name) + delta - 1)
    setattr(motor_data, previous_name, sequence)

  # ------------------ PUBLIC: RX drain & VESC decode ------------------
  def update_motor_data(self, motor_1, motor_2=None, max_frames=32):
    """
    Drain at most max_frames already queued, without waiting for new frames.
    Decodes a subset of VESC CAN status packets into MotorData.
    """
    if Motor._can is None:
      return 0

    frames_processed = 0
    while frames_processed < max_frames:
      tup = self._recv_nonblock()
      if not tup:
        break
      frames_processed += 1

      try:
        message_id_full, is_ext, rtr, data = tup
      except Exception:
        continue
      if not data:
        continue

      # Extract command and node id from extended VESC id
      message_id = (message_id_full >> 8) & 0xFF
      can_id     = message_id_full & 0xFF

      if can_id == motor_1.data.cfg.can_id:
        motor_data = motor_1.data
      elif (motor_2 is not None) and (can_id == motor_2.data.cfg.can_id):
        motor_data = motor_2.data
      else:
        continue

      dlc = len(data)

      try:
        # Project-private VESC LISP precision battery sample (cmd 101).
        # The one CAN frame keeps filtered voltage/current atomic per VESC.
        # Payload: uint32 mV followed by int32 mA, both big-endian.
        if message_id == 101 and dlc >= 8:
          now = time.ticks_ms()
          voltage_x1000, current_x1000 = struct.unpack_from(">Ii", data, 0)
          if voltage_x1000 > 0:
            motor_data.battery_voltage_measurement_x1000 = voltage_x1000
            motor_data.battery_current_measurement_x1000 = current_x1000
            motor_data.battery_precision_last_update_ms = now
            motor_data.battery_precision_update_counter = (
              motor_data.battery_precision_update_counter + 1) & 0x3fffffff
            motor_data.last_can_data_ms = now

        # Project-private VESC LISP motion telemetry (cmd 102).
        # Payload: int32 ERPM, int16 motor current x10, sequence, flags.
        elif message_id == 102 and dlc >= 8:
          now = time.ticks_ms()
          if motor_data is motor_1.data:
            (motor_data.lisp_speed_erpm,
             motor_data.lisp_motor_current_x10,
             motor_data.lisp_motion_sequence,
             motor_data.lisp_motion_flags) = struct.unpack_from(
               ">lhBB", data, 0)
          else:
            (motor_data.lisp_motor_current_x10,
             motor_data.lisp_motion_sequence,
             motor_data.lisp_motion_flags) = struct.unpack_from(
               ">hBB", data, 4)
          self._record_sequence(
            motor_data, motor_data.lisp_motion_sequence,
            "lisp_motion_sequence_previous", "lisp_motion_loss_count")
          motor_data.lisp_motion_last_update_ms = now
          motor_data.last_can_data_ms = now

        # Project-private VESC LISP slow telemetry (cmd 103).
        # Payload: VESC temp x10, motor temp x10, SOC x1000, sequence, flags.
        elif message_id == 103 and dlc >= 8:
          now = time.ticks_ms()
          if motor_data is motor_1.data:
            (motor_data.lisp_vesc_temperature_x10,
             motor_data.lisp_motor_temperature_x10,
             motor_data.lisp_battery_soc_x1000,
             motor_data.lisp_thermal_sequence,
             motor_data.lisp_thermal_flags) = struct.unpack_from(
               ">HHHBB", data, 0)
          else:
            (motor_data.lisp_vesc_temperature_x10,
             motor_data.lisp_motor_temperature_x10) = struct.unpack_from(
               ">HH", data, 0)
            (motor_data.lisp_thermal_sequence,
             motor_data.lisp_thermal_flags) = struct.unpack_from(
               ">BB", data, 6)
          self._record_sequence(
            motor_data, motor_data.lisp_thermal_sequence,
            "lisp_thermal_sequence_previous", "lisp_thermal_loss_count")
          motor_data.lisp_thermal_last_update_ms = now
          motor_data.last_can_data_ms = now

        # (extend with more decoders as needed)

      except Exception:
        # Decode error (length/type), ignore and continue
        pass
    return frames_processed

  # ------------------ PUBLIC: Commands (fire-and-forget) ------------------

  def set_motor_current_amps(self, value):
    """Set motor target current in Amps."""
    mA = int(value * 1000)
    struct.pack_into(">l", Motor._tx_4, 0, mA)
    self._pack_and_send(Motor._tx_4, 1)  # CAN_PACKET_SET_CURRENT = 1

  def set_motor_current_brake_amps(self, value):
    """Set motor brake/regen current in Amps."""
    mA = int(value * 1000)
    struct.pack_into(">l", Motor._tx_4, 0, mA)
    self._pack_and_send(Motor._tx_4, 2)  # CAN_PACKET_SET_CURRENT_BRAKE = 2

  def set_motor_speed_erpm(self, value):
    """Set motor target speed in ERPM."""
    struct.pack_into(">l", Motor._tx_4, 0, int(value))
    self._pack_and_send(Motor._tx_4, 3)  # CAN_PACKET_SET_RPM = 3

  def set_motor_current_limits(self, min, max):
    """Set motor current limits in Amps."""
    min_mA = int(min * 1000)
    max_mA = int(max * 1000)
    struct.pack_into(">l", Motor._tx_8, 0, min_mA)
    struct.pack_into(">l", Motor._tx_8, 4, max_mA)
    self._pack_and_send(Motor._tx_8, 21)  # CAN_PACKET_SET_CURRENT_LIMITS = 21

  def set_battery_current_limits(self, min, max):
    """Set battery current limits in Amps."""
    min_mA = int(min * 1000)
    max_mA = int(max * 1000)
    struct.pack_into(">l", Motor._tx_8, 0, min_mA)
    struct.pack_into(">l", Motor._tx_8, 4, max_mA)
    self._pack_and_send(Motor._tx_8, 23)  # CAN_PACKET_SET_BATTERY_CURRENT_LIMITS = 23

  # ------------------ Optional: basic state peek ------------------

  def motor_get_can_state(self):
    """Return (state, rx_err, tx_err) if exposed by the driver; otherwise None placeholders."""
    can = Motor._can
    if can is None:
      return (None, None, None)

    state = None
    rx_err = None
    tx_err = None

    # Use hasattr (no getattr as requested)
    if hasattr(can, "state"):
      try:
        state = can.state
      except Exception:
        state = None

    if hasattr(can, "receive_error_count"):
      try:
        rx_err = can.receive_error_count
      except Exception:
        rx_err = None
    elif hasattr(can, "rx_error"):
      try:
        rx_err = can.rx_error
      except Exception:
        rx_err = None

    if hasattr(can, "transmit_error_count"):
      try:
        tx_err = can.transmit_error_count
      except Exception:
        tx_err = None
    elif hasattr(can, "tx_error"):
      try:
        tx_err = can.tx_error
      except Exception:
        tx_err = None

    return (state, rx_err, tx_err)


class MotorData:
  def __init__(self, cfg):
    self.cfg = cfg
    # Targets/config
    self.motor_target_current_limit_max = 0
    self.motor_target_current_limit_min = 0
    self.battery_target_current_limit_max = 0
    self.battery_target_current_limit_min = 0
    self.motor_min_current_start = 0
    self.motor_target_speed = 0.0

    # Live telemetry (decoded from VESC CAN packets)
    self.speed_erpm = 0
    self.wheel_speed = 0
    self.vesc_temperature_x10 = 0
    self.motor_temperature_x10 = 0
    self.motor_current_x10 = 0
    self.battery_current_x10 = 0
    self.battery_voltage_x10 = 0
    # Atomic mV/mA LISP samples used by the resistance estimator and, when
    # fresh, as the preferred operational battery telemetry source.
    self.battery_current_measurement_x1000 = None
    self.battery_voltage_measurement_x1000 = None
    self.battery_soc_x1000 = 0
    self.vesc_fault_code = 0
    self.battery_precision_last_update_ms = 0
    self.battery_precision_update_counter = 0
    self.lisp_speed_erpm = 0
    self.lisp_motor_current_x10 = 0
    self.lisp_motion_sequence = 0
    self.lisp_motion_sequence_previous = None
    self.lisp_motion_loss_count = 0
    self.lisp_motion_flags = 0
    self.lisp_motion_last_update_ms = 0
    self.lisp_vesc_temperature_x10 = 0
    self.lisp_motor_temperature_x10 = 0
    self.lisp_battery_soc_x1000 = 0
    self.lisp_thermal_sequence = 0
    self.lisp_thermal_sequence_previous = None
    self.lisp_thermal_loss_count = 0
    self.lisp_thermal_flags = 0
    self.lisp_thermal_last_update_ms = 0
    self.last_can_data_ms = 0
