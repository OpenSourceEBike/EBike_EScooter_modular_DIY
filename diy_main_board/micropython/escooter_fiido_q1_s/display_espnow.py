# display_espnow_async.py
# MicroPython (ESP32 / ESP32-C3) with uasyncio + aioespnow
import network
import uasyncio as asyncio
import aioespnow
from firmware_common.boards_ids import BoardsIds


class Display:
    """
    Async ESP-NOW link to a display peer.

    - Non-blocking TX via aioespnow.asend()
    - RX handled in a background loop
    - Single-slot mailbox (latest state wins) instead of asyncio.Queue
    - Same ASCII payload format you already use
    """

    def __init__(self, vars, front_motor_data, rear_motor_data, mac_address: bytes, channel: int = 1):
        # External providers
        self._vars = vars
        self._front = front_motor_data
        self._rear = rear_motor_data

        # Bring up STA and (try to) pin the channel so both devices match
        self._sta = network.WLAN(network.STA_IF)
        if not self._sta.active():
            self._sta.active(True)
        try:
            self._sta.config(channel=channel)
        except Exception:
            # Some firmwares lock channel if already associated; ignore
            pass

        # (Optional) ensure AP is off to avoid channel clashes
        try:
            ap = network.WLAN(network.AP_IF)
            if ap.active():
                ap.active(False)
        except Exception:
            pass

        # Async ESP-NOW
        self._esp = aioespnow.AIOESPNow()
        self._esp.active(True)

        # Peer MAC (bytes-like of length 6)
        self._peer_mac = bytes(mac_address)
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
            # Peer may already exist
            pass

        # --- mailbox (no Queue available on some builds) ---
        self._mailbox_payload = None          # bytes or None
        self._mailbox_event = asyncio.Event() # "new payload ready" flag

        # Background tasks
        self._rx_task = None
        self._tx_task = None

        # Optional TX rate limit (seconds); 0 disables
        self._min_send_period = 0.0
        self._last_send_ts = 0.0

        self._stopping = False

    # ---------- lifecycle ----------

    async def start(self):
        """Start background RX and TX loops."""
        if self._rx_task is None:
            self._rx_task = asyncio.create_task(self._rx_loop())
        if self._tx_task is None:
            self._tx_task = asyncio.create_task(self._tx_loop())

    async def stop(self):
        """Stop loops and deactivate ESP-NOW."""
        self._stopping = True
        for t in (self._rx_task, self._tx_task):
            if t:
                t.cancel()
        await asyncio.sleep(0)  # let cancellations propagate
        self._rx_task = None
        self._tx_task = None
        try:
            self._esp.active(False)
        except Exception:
            pass

    # ---------- public API ----------

    def queue_send(self):
        """
        Build and place one status frame in the mailbox (non-blocking).
        Overwrites any older unsent frame: latest state wins.
        """
        try:
            payload = self._build_payload().encode("ascii")
            self._mailbox_payload = payload
            self._mailbox_event.set()  # wake the TX loop
        except Exception as e:
            print("Display queue_send error:", e)

    def receive_process_data(self):
        """
        Kept only for compatibility with your old sync design.
        RX is handled continuously in _rx_loop(), so this is a no-op.
        """
        return

    # ---------- background tasks ----------

    async def _tx_loop(self):
        """Drain mailbox and send frames using aioespnow.asend()."""
        try:
            while not self._stopping:
                # Wait for a new payload
                await self._mailbox_event.wait()

                # Grab the latest payload and clear the flag
                payload = self._mailbox_payload
                self._mailbox_event.clear()

                if payload is None:
                    continue

                # Optional rate limit
                if self._min_send_period:
                    now = asyncio.time()
                    dt = now - self._last_send_ts
                    if dt < self._min_send_period:
                        await asyncio.sleep(self._min_send_period - dt)

                try:
                    ok = await self._esp.asend(self._peer_mac, payload)
                    self._last_send_ts = asyncio.time()

                    if not ok:
                        # Peer may have been evicted; re-add and retry once
                        try:
                            self._esp.add_peer(self._peer_mac)
                            await self._esp.asend(self._peer_mac, payload)
                        except OSError as oe:
                            # ETIMEDOUT (116) is common; ignore quietly
                            if not (oe.args and oe.args[0] == 116):
                                print("Display tx error:", oe)
                except OSError as e:
                    if not (e.args and e.args[0] == 116):  # ignore ETIMEDOUT
                        print("Display tx error:", e)
                except Exception as e:
                    print("Display tx error:", e)
        except asyncio.CancelledError:
            pass

    async def _rx_loop(self):
        """Process incoming control frames continuously."""
        try:
            async for mac, msg in self._esp:
                if not msg:
                    continue
                # Expect ASCII: "MAIN_BOARD_ID motors_enable buttons"
                try:
                    parts = [int(s) for s in msg.decode("ascii").split()]
                except Exception:
                    continue

                if (len(parts) == 3) and (int(parts[0]) == int(BoardsIds.MAIN_BOARD)):
                    self._vars.motors_enable_state = (parts[1] != 0)
                    self._vars.buttons_state = parts[2]

                # Keep dynamic peers known (harmless if already added)
                try:
                    self._esp.add_peer(mac)
                except OSError:
                    pass

                if self._stopping:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("Display rx error:", e)

    # ---------- helpers ----------

    def _build_payload(self) -> str:
        """Compose one ASCII status frame compatible with your receiver."""
        brakes_are_active = 1 if self._vars.brakes_are_active else 0
        battery_current_x100 = int(self._front.battery_current_x100 + self._rear.battery_current_x100)
        motor_current_x100   = int(self._front.motor_current_x100   + self._rear.motor_current_x100)

        vesc_temperature_x10  = max(self._front.vesc_temperature_x10,  self._rear.vesc_temperature_x10)
        motor_temperature_x10 = max(self._front.motor_temperature_x10, self._rear.motor_temperature_x10)

        return (
            f"{int(BoardsIds.DISPLAY)} "
            f"{int(self._rear.battery_voltage_x10)} "
            f"{battery_current_x100} "
            f"{int(self._rear.battery_soc_x1000)} "
            f"{motor_current_x100} "
            f"{int(self._rear.wheel_speed * 10)} "
            f"{int(brakes_are_active)} "
            f"{int(vesc_temperature_x10)} "
            f"{int(motor_temperature_x10)}"
        )
