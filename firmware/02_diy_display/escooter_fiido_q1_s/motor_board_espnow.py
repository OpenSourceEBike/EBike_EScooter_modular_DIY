# motor_board_espnow.py
# MicroPython (ESP32-S3) — ESP-NOW MotorBoard using synchronous espnow.

import espnow
from common.boards_ids import BoardsIds

class MotorBoard:
    """
    Bidirectional ESP-NOW link for the motor board, synchronous version.

    - Uses a shared espnow.ESPNow() instance (created in main).
    - RX: chama motor.poll_rx() regularmente para ler a fila ESP-NOW,
      depois motor.receive_process_data() para aplicar os dados aos vars.
    - TX: chama motor.send_data() quando quiseres enviar estado para o motor.
    """

    def __init__(self, espnow_inst: espnow.ESPNow, peer_mac: bytes, vars):
        if not isinstance(espnow_inst, espnow.ESPNow):
            raise TypeError("espnow_inst must be an espnow.ESPNow instance")

        self._esp = espnow_inst
        self._peer_mac = bytes(peer_mac)
        if len(self._peer_mac) != 6:
            raise ValueError("peer_mac must be 6 bytes")
        self._vars = vars

        # Ensure peer exists (harmless if already added)
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
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
            print("MotorBoard rx error:", e)
            return

        if not last_msg:
            return

        try:
            parts = [int(s) for s in last_msg.decode("ascii").split()]
        except Exception as ex:
            print(ex)
            return

        if (len(parts) == 9) and (int(parts[0]) == int(BoardsIds.DISPLAY)):
            self._vars.battery_voltage_x10   = parts[1]
            self._vars.battery_current_x10   = parts[2]
            self._vars.battery_soc_x1000     = parts[3]
            self._vars.motor_current_x10     = parts[4]
            self._vars.wheel_speed_x10       = parts[5]

            flags = parts[6]
            self._vars.brakes_are_active       = bool(flags & (1 << 0))
            self._vars.regen_braking_is_active = bool(flags & (1 << 1))
            self._vars.battery_is_charging     = bool(flags & (1 << 2))
            self._vars.mode = (flags >> 3) & 0x07

            self._vars.vesc_temperature_x10  = parts[7]
            self._vars.motor_temperature_x10 = parts[8]

    # ---------- TX path ----------
    def _build_tx_payload(self) -> bytes:
        motor_enable_state = 1 if self._vars.motor_enable_state else 0
        return f"{int(BoardsIds.MAIN_BOARD)} {motor_enable_state} {self._vars.buttons_state}".encode("ascii")

    def send_data(self):
        """
        Non-blocking.
        
        Call this frequently from your main loop.
        """
        payload = self._build_tx_payload()
        try:
            ok = self._esp.send(self._peer_mac, payload)
            if ok is False:
                # (re)add peer and retry once
                try:
                    self._esp.add_peer(self._peer_mac)
                except OSError:
                    pass
                try:
                    self._esp.send(self._peer_mac, payload)
                except Exception:
                    pass
        except OSError as e:
            # Many ports use 116 for ETIMEDOUT; keep quiet to avoid spam
            if not (e.args and e.args[0] == 116):
                print("MotorBoard tx error:", e)
        except Exception as e:
            print("MotorBoard tx error:", e)
