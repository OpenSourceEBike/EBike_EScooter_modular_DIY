# power_switch_espnow.py
# MicroPython ESP-NOW helper for the power switch (synchronous espnow).

import espnow
from common.boards_ids import BoardsIds


class PowerSwitch:
    """
    Send power-switch state over ESP-NOW (synchronous version).

    Args:
        espnow_inst (espnow.ESPNow): active instance (espnow_inst.active(True) done by caller)
        peer_mac (bytes): 6-byte MAC of the receiver (motor board)
        vars: object exposing .turn_off_relay (bool)
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

        self._comm_count = 0

    # ---------- payload ----------
    def _build_payload(self) -> bytes:
        self._comm_count += 1
        if self._comm_count > 1024:
            self._comm_count = 0

        turn_off_relay = 1 if self._vars.turn_off_relay else 0
        return f"{int(BoardsIds.POWER_SWITCH)} {self._comm_count} {turn_off_relay}".encode("ascii")

    # ---------- public API ----------
    def send_data(self):
        """
        Synchronous send (no asyncio).
        Call from o teu loop principal sempre que quiseres atualizar o estado.
        """
        payload = self._build_payload()
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
            if not (e.args and e.args[0] == 116):
                print("PowerSwitch tx error:", e)
        except Exception as e:
            print("PowerSwitch tx error:", e)
