# rear_lights_espnow.py
# MicroPython ESP-NOW helper for the rear lights (synchronous espnow).

import espnow
from common.boards_ids import BoardsIds


class RearLights:
    """
    Send rear-lights state over ESP-NOW (synchronous version).

    Args:
        espnow_inst (espnow.ESPNow): active instance (espnow_inst.active(True) done by caller)
        peer_mac (bytes): 6-byte MAC of the receiver (rear lights board)
        system_data: object exposing .rear_lights_board_pins_state (int/bool)
    """

    def __init__(self, espnow_inst: espnow.ESPNow, peer_mac: bytes, system_data):
        if not isinstance(espnow_inst, espnow.ESPNow):
            raise TypeError("espnow_inst must be an espnow.ESPNow instance")

        self._esp = espnow_inst
        self._peer_mac = bytes(peer_mac)
        if len(self._peer_mac) != 6:
            raise ValueError("peer_mac must be 6 bytes")
        self._system_data = system_data

        # Ensure peer exists (harmless if already added)
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
            pass

    # ---------- payload ----------
    def _build_payload(self) -> bytes:
        try:
            pins_state = int(getattr(self._system_data, "rear_lights_board_pins_state", 0))
        except Exception:
            pins_state = 0
        return f"{int(BoardsIds.REAR_LIGHTS)} {pins_state}".encode("ascii")

    # ---------- public API ----------
    def send_data(self):
        """
        Synchronous send (no asyncio).
        Call from o teu loop principal com a cadência que quiseres (p.ex. 20 Hz).
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
                print("RearLights tx error:", e)
        except Exception as e:
            print("RearLights tx error:", e)
