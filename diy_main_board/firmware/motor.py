import time
import struct
from can import CAN

# Common errno values that appear on various ports/usermods
_EAGAIN    = 11      # resource temporarily unavailable (queue full)
_EBUSY     = 16      # busy
_ETIMEDOUT = 110     # timeout
_ENOTCONN  = 107
_ECONNRST  = 104
_ETXFAIL   = 0x0107


class Motor(object):
    _can = None                 # shared CAN instance (singleton)
    _tx_4 = bytearray(4)
    _tx_8 = bytearray(8)

    def __init__(self, data):
        self.data = data

        # TX health counters (simple observability)
        self.tx_ok = 0
        self.tx_drop = 0
        self.last_tx_error = None  # tuple(code, repr)

        # Configure CAN once (singleton-style)
        if (self.data.cfg.can_tx_pin is not None) and (self.data.cfg.can_rx_pin is not None):
            if Motor._can is None:
                # Prefer your cfg pins and params if available
                tx_pin = getattr(self.data.cfg, "can_tx_pin", 2) or 2
                rx_pin = getattr(self.data.cfg, "can_rx_pin", 3) or 3
                baud   = getattr(self.data.cfg, "can_baudrate", 125000) or 125000
                mode   = getattr(self.data.cfg, "can_mode", 0) or 0  # 0 = normal

                Motor._can = CAN(
                    tx=tx_pin,
                    rx=rx_pin,
                    baudrate=baud,
                    mode=mode
                )

    # ------------------ INTERNAL: TX (never raise) ------------------

    def _pack_and_send(self, buf, command) -> bool:
        """
        Fire-and-forget send. Never raises on TX error; drops frame instead.
        Returns True on success, False if dropped.
        """
        if Motor._can is None:
            self.last_tx_error = ("NO_CAN", "CAN not initialized")
            self.tx_drop += 1
            return False

        msg_id = (self.data.cfg.can_id | (command << 8))  # VESC-style id packing

        try:
            # Non-blocking send: if queue full, driver may raise OSError
            Motor._can.send(buf, msg_id, extframe=True, timeout=0)
            self.tx_ok += 1
            # tiny yield to avoid starving other tasks
            time.sleep_ms(3)
            return True

        except OSError as e:
            code = e.args[0] if e.args else None
            self.last_tx_error = (code, repr(e))
            self.tx_drop += 1
            # Silent drop for known transient/frequent errors
            if code in (_EAGAIN, _EBUSY, _ETIMEDOUT, _ENOTCONN, _ECONNRST, _ETXFAIL, None):
                return False
            # Unknown error -> still don't raise
            return False

        except Exception as e:
            self.last_tx_error = ("EXC", repr(e))
            self.tx_drop += 1
            return False

    # ------------------ INTERNAL: RX (never block) ------------------

    @staticmethod
    def _recv_nonblock():
        can = Motor._can
        if not can:
            return None
        try:
            return can.recv()
        except OSError as e:
            return None
        except Exception:
            return None

    # ------------------ PUBLIC: RX draining & decode ------------------

    def update_motor_data(self, motor_1, motor_2=None, budget_ms=10):
        """
        Drain frames for ~budget_ms without blocking the system.
        Decodes a subset of VESC CAN status packets into MotorData.
        """
        if Motor._can is None:
            return

        end_at = time.ticks_add(time.ticks_ms(), budget_ms)
        while time.ticks_diff(end_at, time.ticks_ms()) > 0:
            tup = self._recv_nonblock()
            if not tup:
                # brief yield to avoid tight spin when bus idle
                time.sleep_us(300)
                continue

            # Unpack safely
            try:
                message_id_full, _, _, data = tup
            except Exception:
                continue
            if not data:
                continue
            
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
                if message_id == 9 and dlc >= 6:     # CAN_PACKET_STATUS_1
                    motor_data.speed_erpm         = struct.unpack_from(">l", data, 0)[0]
                    motor_data.motor_current_x100 = struct.unpack_from(">h", data, 4)[0]

                elif message_id == 16 and dlc >= 6:  # CAN_PACKET_STATUS_4
                    motor_data.vesc_temperature_x10  = struct.unpack_from(">h", data, 0)[0]
                    motor_data.motor_temperature_x10 = struct.unpack_from(">h", data, 2)[0]
                    motor_data.battery_current_x100  = struct.unpack_from(">h", data, 4)[0]

                elif message_id == 27 and dlc >= 6:  # CAN_PACKET_STATUS_5
                    motor_data.battery_voltage_x10 = struct.unpack_from(">h", data, 4)[0]

                elif message_id == 99 and dlc >= 2:  # CAN_PACKET_STATUS_7
                    motor_data.battery_soc_x1000 = struct.unpack_from(">h", data, 0)[0]

                # Add other packet decoders here as needed

            except Exception:
                # Malformed frame or unexpected length; ignore and continue
                pass
            
    # ------------------ PUBLIC: Commands (fire-and-forget) ------------------

    def set_motor_current_amps(self, value):
        """Set motor target current in Amps"""
        mA = int(value * 1000)
        struct.pack_into(">l", Motor._tx_4, 0, mA)
        self._pack_and_send(Motor._tx_4, 1)  # CAN_PACKET_SET_CURRENT = 1

    def set_motor_current_brake_amps(self, value):
        """Set motor current brake / regen Amps"""
        mA = int(value * 1000)
        struct.pack_into(">l", Motor._tx_4, 0, mA)
        self._pack_and_send(Motor._tx_4, 2)  # CAN_PACKET_SET_CURRENT_BRAKE = 2

    def set_motor_speed_rpm(self, value):
        """Set motor speed in RPM"""
        struct.pack_into(">l", Motor._tx_4, 0, int(value))
        self._pack_and_send(Motor._tx_4, 3)  # CAN_PACKET_SET_RPM = 3

    def set_motor_current_limits(self, min, max):
        """Set motor current limits in Amps"""
        min_mA = int(min * 1000)
        max_mA = int(max * 1000)
        struct.pack_into(">l", Motor._tx_8, 0, min_mA)
        struct.pack_into(">l", Motor._tx_8, 4, max_mA)
        self._pack_and_send(Motor._tx_8, 21)  # CAN_PACKET_SET_CURRENT_LIMITS = 21

    def set_battery_current_limits(self, min, max):
        """Set battery current limits in Amps"""
        min_mA = int(min * 1000)
        max_mA = int(max * 1000)
        struct.pack_into(">l", Motor._tx_8, 0, min_mA)
        struct.pack_into(">l", Motor._tx_8, 4, max_mA)
        self._pack_and_send(Motor._tx_8, 23)  # CAN_PACKET_SET_BATTERY_CURRENT_LIMITS = 23

    # ------------------ Optional: basic state peek ------------------

    def motor_get_can_state(self):
        can = Motor._can
        if can is None:
            return (None, None, None)
        # usermod may not expose these; getattr fallbacks keep it safe
        return (
            getattr(can, "state", None),
            getattr(can, "rx_error", None) or getattr(can, "receive_error_count", None),
            getattr(can, "tx_error", None) or getattr(can, "transmit_error_count", None),
        )


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

        # Live telemetry
        self.speed_erpm = 0
        self.wheel_speed = 0
        self.vesc_temperature_x10 = 0
        self.motor_temperature_x10 = 0
        self.motor_current_x100 = 0
        self.battery_current_x100 = 0
        self.battery_voltage_x10 = 0
        self.battery_soc_x1000 = 0
        self.vesc_fault_code = 0
