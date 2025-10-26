import time
import network
import uasyncio as asyncio
import aioespnow
from common.boards_ids import BoardsIds
from configurations_escooter_fiido_q1_s import cfg

class Display:
    """
    MicroPython ESP-NOW Display link.
    """
    
    battery_current_x10 = 0

    def __init__(self, vars, front_motor_data, rear_motor_data, mac_address: bytes, channel: int = 1):
        # Providers (may be partially uninitialized at boot)
        self._vars  = vars
        self._front = front_motor_data
        self._rear  = rear_motor_data

        # Wi-Fi STA on desired channel; AP off
        sta = network.WLAN(network.STA_IF)
        self._sta = sta
        if not sta.active():
            sta.active(True)
        try:
            try: sta.disconnect()
            except Exception: pass
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
            import configurations_escooter_fiido_q1_s as conf
            my_mac = bytes(conf.cfg.my_mac_address)
            self._sta.config(mac=my_mac)
        except Exception as e:
            print("Warning: couldn't fix local MAC:", e)

        # ESP-NOW
        self._esp = aioespnow.AIOESPNow()
        self._esp.active(True)

        # Peer MAC
        self._peer_mac = bytes(mac_address)
        if len(self._peer_mac) != 6:
            raise ValueError("Peer MAC must be 6 bytes")
        try:
            self._esp.add_peer(self._peer_mac)
        except OSError:
            pass  # already there

        # --- TX mailbox (single-slot, latest wins) ---
        self._mailbox_payload = None
        self._mailbox_event   = asyncio.Event()

        # --- RX latest (single-slot) ---
        # Holds the *latest* raw message bytes from any peer until consumed.
        self._rx_latest = None

        # Background tasks
        self._rx_task = None
        self._tx_task = None
        self._stopping = False

        # Debug banner (ASCII only)
        mac_self = ":".join(f"{x:02X}" for x in self._sta.config("mac"))
        peer_str = ":".join(f"{x:02X}" for x in self._peer_mac)

    # ---------- lifecycle ----------

    async def start(self):
        """Start background RX/TX loops (must be awaited once)."""
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
        await asyncio.sleep(0)
        self._rx_task = None
        self._tx_task = None
        try:
            self._esp.active(False)
        except Exception:
            pass

    # ---------- public API (same names as your CP version) ----------

    def receive_process_data(self):
        """
        Non-blocking: apply the most recent control packet if one arrived.
        """
        msg = self._rx_latest
        if not msg:
            return
        # consume it
        self._rx_latest = None
        try:
            parts = [int(n) for n in msg.split()]
        except Exception as ex:
            print(ex)
            return

        if (len(parts) == 3) and (int(parts[0]) == int(BoardsIds.MAIN_BOARD)):
            self._vars.motors_enable_state = (parts[1] != 0)
            self._vars.buttons_state = parts[2]

    def send_data(self):
        """
        Build and enqueue one status frame (non-blocking).
        """
        try:
            brakes_are_active = 1 if self._vars.brakes_are_active else 0
            regen_braking_is_active = 1 if self._vars.regen_braking_is_active else 0
            battery_is_charging = 1 if self._vars.battery_is_charging else 0
            
            if not cfg.has_jbd_bms:
                battery_is_charging = 0
                
            #print(brakes_are_active, regen_braking_is_active, battery_is_charging)

            # guard providers (None-safe)
            def _i(v): 
                try: return int(v)
                except Exception: return 0
            def _ix10(v):
                try: return int(v * 10)
                except Exception: return 0

            battery_current_x10 = self._front.battery_current_x10 + \
                                    self._rear.battery_current_x10
                                    
            motor_current_x10 = self._front.motor_current_x10 + \
                                    self._rear.motor_current_x10

            vesc_temperature_x10 = max(self._front.vesc_temperature_x10,
                                    self._rear.vesc_temperature_x10)
            
            motor_temperature_x10 = max(self._front.motor_temperature_x10,
                                    self._rear.motor_temperature_x10)

            flags = ((brakes_are_active & 1) << 0) | \
                    ((regen_braking_is_active & 1) << 1) | \
                    ((battery_is_charging & 1) << 2)

            payload = (
                f"{int(BoardsIds.DISPLAY)} "
                f"{self._rear.battery_voltage_x10} "
                f"{battery_current_x10} "
                f"{self._rear.battery_soc_x1000} "
                f"{motor_current_x10} "
                f"{int(self._rear.wheel_speed * 10)} "
                f"{flags} "
                f"{vesc_temperature_x10} "
                f"{motor_temperature_x10}"
            ).encode("ascii")

            self._mailbox_payload = payload
            self._mailbox_event.set()
        except Exception as e:
            print("Display tx error:", e)

    # ---------- background tasks ----------

    async def _tx_loop(self):
        try:
            while not self._stopping:
                await self._mailbox_event.wait()
                payload = self._mailbox_payload
                self._mailbox_event.clear()
                if payload is None:
                    continue
                try:
                    ok = await self._esp.asend(self._peer_mac, payload)
                    if not ok:
                        # (re)add peer and try once more; harmless if already added
                        try:
                            self._esp.add_peer(self._peer_mac)
                            await self._esp.asend(self._peer_mac, payload)
                        except OSError:
                            pass
                except OSError as e:
                    # many ports use 116 for ETIMEDOUT; ignore
                    if not (e.args and e.args[0] == 116):
                        print("Display tx error:", e)
                except Exception as e:
                    print("Display tx error:", e)
        except asyncio.CancelledError:
            pass

    async def _rx_loop(self):
        try:
            async for mac, msg in self._esp:
                if not msg:
                    continue
                # Keep only the latest
                self._rx_latest = msg
                # keep dynamic peer (harmless if already added)
                try:
                    self._esp.add_peer(mac)
                except OSError:
                    pass
                if self._stopping:
                    break
        except asyncio.CancelledError:
            return
        except Exception as e:
            print("Display rx error:", e)
