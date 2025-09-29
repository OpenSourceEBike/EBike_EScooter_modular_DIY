# motor_board.py
# MicroPython (ESP32/ESP32-C3) — ESP-NOW MotorBoard using aioespnow only.

import uasyncio as asyncio
import aioespnow
from firmware_common.boards_ids import BoardsIds


class MotorBoard:
    """
    Bidirectional ESP-NOW link for the motor board.
    """

    def __init__(self, esp: aioespnow.AIOESPNow, peer_mac: bytes, system_data):
        if not isinstance(esp, aioespnow.AIOESPNow):
            raise TypeError("esp must be an aioespnow.AIOESPNow instance")

        self._esp = esp
        self._peer_mac = bytes(peer_mac)
        if len(self._peer_mac) != 6:
            raise ValueError("peer_mac must be 6 bytes")
        self._system_data = system_data

        # Ensure peer exists (harmless if already added)
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
            pass

        # RX latest message buffer (bytes)
        self._rx_latest = None

        # Tasks / locks
        self._rx_task = None
        self._stopping = False
        self._send_lock = asyncio.Lock()

    # ---------- lifecycle ----------
    async def start(self):
        """Start background RX loop."""
        if self._rx_task is None:
            self._stopping = False
            self._rx_task = asyncio.create_task(self._rx_loop())

    async def stop(self):
        """Stop background RX loop."""
        self._stopping = True
        t = self._rx_task
        self._rx_task = None
        if t:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    # ---------- RX path (background) ----------
    async def _rx_loop(self):
        try:
            async for mac, msg in self._esp:
                if self._stopping:
                    break
                if not msg:
                    continue
                # Keep latest only
                self._rx_latest = msg
                # Keep dynamic peer (harmless if already added)
                try:
                    self._esp.add_peer(mac)
                except OSError:
                    pass
        except asyncio.CancelledError:
            return
        except Exception as e:
            print("rx loop error:", e)

    def receive_process_data(self):
        """
        Non-blocking: decode & apply the most recent DISPLAY frame, if any.
        Expects 9 integers as described in the class docstring.
        """
        msg = self._rx_latest
        if not msg:
            return
        # consume it
        self._rx_latest = None

        try:
            parts = [int(s) for s in msg.decode("ascii").split()]
        except Exception:
            return

        if len(parts) != 9:
            return
        if parts[0] != int(BoardsIds.DISPLAY):
            return

        try:
            self._system_data.battery_voltage_x10   = parts[1]
            self._system_data.battery_current_x100  = parts[2]
            self._system_data.battery_soc_x1000     = parts[3]
            self._system_data.motor_current_x100    = parts[4]
            self._system_data.wheel_speed_x10       = parts[5]
            self._system_data.brakes_are_active     = (parts[6] == 1)
            self._system_data.vesc_temperature_x10  = parts[7]
            self._system_data.motor_temperature_x10 = parts[8]
            
        except Exception as e:
            print("rx apply error:", e)

    # ---------- TX path ----------
    def _build_tx_payload(self) -> bytes:
        
        motor_enable_state = 1 if self._system_data.motor_enable_state else 0

        return f"{int(BoardsIds.MAIN_BOARD)} {motor_enable_state} {self._system_data.buttons_state}".encode("ascii")

    def send_data(self):
        """Fire-and-forget send using aioespnow (schedules an async task)."""
        payload = self._build_tx_payload()
        asyncio.create_task(self._asend_bg(payload))

    async def send_data_async(self):
        """Awaitable variant."""
        payload = self._build_tx_payload()
        await self._asend_bg(payload)

    async def _asend_bg(self, payload: bytes):
        async with self._send_lock:
            try:
                ok = await self._esp.asend(self._peer_mac, payload)
            except OSError as e:
                # Many ports use 116 for ETIMEDOUT; keep quiet to avoid spam
                if not (e.args and e.args[0] == 116):
                    print("MotorBoard tx error:", e)
            except Exception as e:
                print("MotorBoard tx error:", e)
