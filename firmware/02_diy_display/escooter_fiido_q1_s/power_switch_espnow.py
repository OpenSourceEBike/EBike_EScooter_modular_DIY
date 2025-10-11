import uasyncio as asyncio
import aioespnow
from common.boards_ids import BoardsIds

class PowerSwitch:
    """
    Send power-switch state over ESP-NOW.
    """

    def __init__(self, espnow: aioespnow.AIOESPNow, peer_mac: bytes, radio_lock: asyncio.Lock, vars):
        if not isinstance(espnow, aioespnow.AIOESPNow):
            raise TypeError("espnow must be an aioespnow.AIOESPNow instance")

        self._espnow = espnow
        self._peer_mac = bytes(peer_mac)
        if len(self._peer_mac) != 6:
            raise ValueError("peer_mac must be 6 bytes")
        self._vars = vars

        # Ensure peer exists (harmless if already added)
        try:
            self._espnow.add_peer(self._peer_mac)
        except OSError as ex:
            print(ex)

        self._comm_count = 0
        self._send_lock = radio_lock

    # ---------- payload ----------
    def _build_payload(self) -> bytes:
        self._comm_count += 1
        if self._comm_count > 1024:
            self._comm_count = 0
        
        turn_off_relay = 1 if self._vars.turn_off_relay else 0
        return f"{int(BoardsIds.POWER_SWITCH)} {self._comm_count} {turn_off_relay}".encode("ascii")

    # ---------- public API ----------
    def send_data(self):
        """Fire-and-forget: schedule an async ESP-NOW send."""
        payload = self._build_payload()
        asyncio.create_task(self._asend_bg(payload))

    async def send_data_async(self):
        """Awaitable variant."""
        print('abc')
        payload = self._build_payload()
        await self._asend_bg(payload)

    # ---------- internals ----------
    async def _asend_bg(self, payload: bytes):
        async with self._send_lock:
            try:
                ok = await self._espnow.asend(self._peer_mac, payload)
                print('sent')
                if not ok:
                    print('nok')
                    # (re)add peer and retry once
                    try:
                        self._espnow.add_peer(self._peer_mac)
                    except OSError:
                        pass
                    try:
                        await self._espnow.asend(self._peer_mac, payload)
                    except Exception:
                        pass
            except OSError as e:
                # Many ports use 116 for ETIMEDOUT; keep quiet to avoid spam
                if not (e.args and e.args[0] == 116):
                    print("PowerSwitch tx error:", e)
            except Exception as e:
                print("PowerSwitch tx error:", e)
