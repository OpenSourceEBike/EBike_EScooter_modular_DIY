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
            time.sleep_ms(3)  # small yield to avoid starving REPL/USB/CAN IRQs
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

    # ------------------ PUBLIC: RX drain & VESC decode ------------------

    def update_motor_data(self, motor_1, motor_2=None, budget_ms=10):
        """
        Drain frames for ~budget_ms without blocking.
        Decodes a subset of VESC CAN status packets into MotorData.
        """
        if Motor._can is None:
            return

        end_at = time.ticks_add(time.ticks_ms(), budget_ms)
        while time.ticks_diff(end_at, time.ticks_ms()) > 0:
            tup = self._recv_nonblock()
            if not tup:
                time.sleep_us(300)  # tiny yield when bus idle
                continue

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
                # CAN_PACKET_STATUS_1 (cmd 9)
                if message_id == 9 and dlc >= 6:
                    motor_data.speed_erpm          = struct.unpack_from(">l", data, 0)[0]
                    motor_data.motor_current_x10   = struct.unpack_from(">h", data, 4)[0]

                # CAN_PACKET_STATUS_4 (cmd 16)
                elif message_id == 16 and dlc >= 6:
                    motor_data.vesc_temperature_x10  = struct.unpack_from(">h", data, 0)[0]
                    motor_data.motor_temperature_x10 = struct.unpack_from(">h", data, 2)[0]
                    motor_data.battery_current_x10   = struct.unpack_from(">h", data, 4)[0]

                # CAN_PACKET_STATUS_5 (cmd 27)
                elif message_id == 27 and dlc >= 6:
                    motor_data.battery_voltage_x10 = struct.unpack_from(">h", data, 4)[0]

                # CAN_PACKET_STATUS_7 (cmd 99)
                elif message_id == 99 and dlc >= 2:
                    motor_data.battery_soc_x1000 = struct.unpack_from(">h", data, 0)[0]

                # (extend with more decoders as needed)

            except Exception:
                # Decode error (length/type), ignore and continue
                pass

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

    def set_motor_speed_rpm(self, value):
        """Set motor target speed in mechanical RPM."""
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
        self.battery_soc_x1000 = 0
        self.vesc_fault_code = 0
