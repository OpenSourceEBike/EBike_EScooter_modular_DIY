import time
import network
import espnow
from common.boards_ids import BoardsIds
from common.config_runtime import cfg


class Display:
    """
    MicroPython ESP-NOW Display link.
    """

    battery_current_x10 = 0

    def __init__(self, vars, rear_motor_data,
                 mac_address: bytes, channel: int = 1):
        # Providers (may be partially uninitialized at boot)
        self._vars  = vars
        self._rear  = rear_motor_data

        # Wi-Fi STA on desired channel; AP off
        sta = network.WLAN(network.STA_IF)
        self._sta = sta
        if not sta.active():
            sta.active(True)
        try:
            try:
                sta.disconnect()
            except Exception:
                pass
            sta.config(channel=channel)
        except Exception:
            pass
        try:
            ap = network.WLAN(network.AP_IF)
            if ap.active():
                ap.active(False)
        except Exception:
            pass

        try:
            # define local MAC
            my_mac = bytes(cfg.my_mac_address)
            self._sta.config(mac=my_mac)
        except Exception as e:
            print("Warning: couldn't fix local MAC:", e)

        # ESP-NOW
        self._esp = espnow.ESPNow()
        self._esp.active(True)

        # Peer MAC
        self._peer_mac = bytes(mac_address)
        if len(self._peer_mac) != 6:
            raise ValueError("Peer MAC must be 6 bytes")
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
            # already there
            pass

    # ---------- public API ----------
    def receive_process_data(self):
        """
        Non-blocking: read any pending ESP-NOW packets and apply
        the most recent control packet if one arrived.

        Call this frequently from your main loop.
        """
        last_msg = None
        try:
            while True:
                host, msg = self._esp.recv(0)  # timeout=0 -> non-blocking
                if not msg:
                    break
                last_msg = msg

                # keep dynamic peer (harmless if already added)
                try:
                    self._esp.add_peer(host)
                except OSError:
                    pass
        except OSError:
            # no messages or minor recv error
            pass
        except Exception as e:
            print("Display rx error:", e)
            return

        if not last_msg:
            return

        try:
            parts = [int(n) for n in last_msg.split()]
        except Exception as ex:
            print(ex)
            return

        if (len(parts) == 3) and (int(parts[0]) == int(BoardsIds.MAIN_BOARD)):
            self._vars.motors_enable_state = (parts[1] != 0)
            self._vars.buttons_state = parts[2]

    def send_data(self):
        """
        Build and send one status frame.
        Call this periodically from your loop or task.
        """
        try:
            brakes_are_active = 1 if self._vars.brakes_are_active else 0
            regen_braking_is_active = 1 if self._vars.regen_braking_is_active else 0
            battery_is_charging = 1 if self._vars.battery_is_charging else 0

            if not cfg.has_jbd_bms:
                battery_is_charging = 0

            # guard providers (None-safe)
            def _i(v):
                try:
                    return int(v)
                except Exception:
                    return 0
            def _f(v):
                try:
                    return float(v)
                except Exception:
                    return 0.0

            battery_current_x10 = _i(self._rear.battery_current_x10)
            motor_current_x10 = _i(self._rear.motor_current_x10)
            vesc_temperature_x10 = _i(self._rear.vesc_temperature_x10)
            motor_temperature_x10 = _i(self._rear.motor_temperature_x10)

            flags = ((brakes_are_active & 1) << 0) | \
                    ((regen_braking_is_active & 1) << 1) | \
                    ((battery_is_charging & 1) << 2) | \
                    ((self._vars.mode & 7) << 3) # reserve 3 bits for Mode

            payload = (
                f"{int(BoardsIds.DISPLAY)} "
                f"{_i(self._rear.battery_voltage_x10)} "
                f"{battery_current_x10} "
                f"{_i(self._rear.battery_soc_x1000)} "
                f"{motor_current_x10} "
                f"{int(_f(self._rear.wheel_speed) * 10)} "
                f"{flags} "
                f"{vesc_temperature_x10} "
                f"{motor_temperature_x10}"
            ).encode("ascii")

            try:
                ok = self._esp.send(self._peer_mac, payload)
                if not ok:
                    # (re)add peer and try once more; harmless if already added
                    try:
                        self._esp.add_peer(self._peer_mac)
                    except OSError:
                        pass
                    try:
                        self._esp.send(self._peer_mac, payload)
                    except Exception:
                        pass
            except OSError as e:
                # many ports use 116 for ETIMEDOUT; ignore quietly
                if not (e.args and e.args[0] == 116):
                    print("Display tx error:", e)
            except Exception as e:
                print("Display tx error:", e)

        except Exception as e:
            print("Display tx build error:", e)
            
