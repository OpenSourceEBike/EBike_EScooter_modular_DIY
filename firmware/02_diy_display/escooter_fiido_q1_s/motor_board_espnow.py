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

        # RX latest message buffer (bytes)
        self._rx_latest = None

    # ---------- RX path ----------
    def poll_rx(self):
        """
        Non-blocking poll of ESP-NOW RX queue.
        Reads all pending packets (timeout=0) and keeps only the last one.
        """
        last_msg = None
        try:
            while True:
                host, msg = self._esp.recv(0)  # non-blocking
                if not msg:
                    break
                last_msg = msg
                # Keep dynamic peer (harmless if already added)
                try:
                    self._esp.add_peer(host)
                except OSError:
                    pass
        except OSError:
            # No messages or minor recv error
            pass
        except Exception as e:
            print("MotorBoard rx poll error:", e)

        if last_msg is not None:
            self._rx_latest = last_msg

    def receive_process_data(self):
        """
        Decode & apply the most recent DISPLAY frame, if any.
        Call this after poll_rx().
        """
        msg = self._rx_latest
        if not msg:
            return

        # consume it
        self._rx_latest = None

        try:
            parts = [int(s) for s in msg.decode("ascii").split()]
        except Exception as ex:
            print(ex)
            return

        if len(parts) != 9:
            return
        if parts[0] != int(BoardsIds.DISPLAY):
            return

        try:
            self._vars.battery_voltage_x10   = parts[1]
            self._vars.battery_current_x10   = parts[2]
            self._vars.battery_soc_x1000     = parts[3]
            self._vars.motor_current_x10     = parts[4]
            self._vars.wheel_speed_x10       = parts[5]

            flags = parts[6]
            self._vars.brakes_are_active       = bool(flags & (1 << 0))
            self._vars.regen_braking_is_active = bool(flags & (1 << 1))
            self._vars.battery_is_charging     = bool(flags & (1 << 2))

            self._vars.vesc_temperature_x10  = parts[7]
            self._vars.motor_temperature_x10 = parts[8]

        except Exception as e:
            print("rx apply error:", e)

    # ---------- TX path ----------
    def _build_tx_payload(self) -> bytes:
        motor_enable_state = 1 if self._vars.motor_enable_state else 0
        return f"{int(BoardsIds.MAIN_BOARD)} {motor_enable_state} {self._vars.buttons_state}".encode("ascii")

    def send_data(self):
        """
        Synchronous send to motor board.
        Call from o teu loop principal sempre que quiseres enviar comando.
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
