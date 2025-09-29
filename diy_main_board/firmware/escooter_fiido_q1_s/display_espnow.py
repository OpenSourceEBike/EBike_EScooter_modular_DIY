import time
import network
import uasyncio as asyncio
import aioespnow
from firmware_common.boards_ids import BoardsIds


class Display:
    """
    MicroPython ESP-NOW Display link, CircuitPython-style API.

    - call await start() once
    - call send_data() whenever you want to transmit the status frame
    - call receive_process_data() periodically to apply the latest control packet
    """
    
    battery_current_x100 = 0

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
            # define o MAC local (usa a tua cfg.my_mac_address como bytes)
            import configurations_escooter_fiido_q1_s as conf
            my_mac = bytes(conf.cfg.my_mac_address)
            self._sta.config(mac=my_mac)
        except Exception as e:
            print("Aviso: não consegui fixar o MAC local:", e)

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
        print(f"[Display] STA {mac_self} ch {self._sta.config('channel')} -> peer {peer_str}")

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
        Expected ASCII: "<MAIN_BOARD> <motors_enable> <buttons>"
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

        if (len(parts) == 3) and (int(parts[0]) == int(BoardsIds.MAIN_BOARD)):
            self._vars.motors_enable_state = (parts[1] != 0)
            self._vars.buttons_state = parts[2]

    def send_data(self):
        """
        Build and enqueue one status frame (non-blocking).
        Payload format identical to your CP version.
        """
        try:
            brakes_are_active = 1 if getattr(self._vars, "brakes_are_active", False) else 0

            # guard providers (None-safe)
            def _i(v): 
                try: return int(v)
                except Exception: return 0
            def _ix10(v):
                try: return int(v * 10)
                except Exception: return 0

            battery_current_x100 = _i(getattr(self._front, "battery_current_x100", 0)) \
                                 + _i(getattr(self._rear,  "battery_current_x100",  0))
            motor_current_x100   = _i(getattr(self._front, "motor_current_x100",   0)) \
                                 + _i(getattr(self._rear,  "motor_current_x100",   0))

            vesc_temperature_x10  = max(_i(getattr(self._front, "vesc_temperature_x10",  0)),
                                        _i(getattr(self._rear,  "vesc_temperature_x10",  0)))
            motor_temperature_x10 = max(_i(getattr(self._front, "motor_temperature_x10", 0)),
                                        _i(getattr(self._rear,  "motor_temperature_x10", 0)))
            
            
            Display.battery_current_x100 += 10
            if Display.battery_current_x100 > 1000:
                Display.battery_current_x100 = 0
            
            battery_voltage_x10 = 720
            print(f'sent to display: {int((Display.battery_current_x100 * battery_voltage_x10)/1000)} W motor power')

            payload = (
                f"{int(BoardsIds.DISPLAY)} "
#                 f"{_i(getattr(self._rear, 'battery_voltage_x10', 0))} "
                f"{battery_voltage_x10} "
                f"{Display.battery_current_x100} "
                f"{_i(getattr(self._rear, 'battery_soc_x1000', 0))} "
                f"{motor_current_x100} "
                f"{_ix10(getattr(self._rear, 'wheel_speed', 0.0))} "
                f"{brakes_are_active} "
                f"{vesc_temperature_x10} "
                f"{motor_temperature_x10}"
            ).encode("ascii")

            self._mailbox_payload = payload
            self._mailbox_event.set()
        except Exception as e:
            print("Display tx error:", e)

    # ---------- background tasks ----------

    async def _tx_loop(self):
        # print("[Display] _tx_loop")
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
        # print("[Display] _rx_loop")
        try:
            async for mac, msg in self._esp:
                if not msg:
                    continue
                # Keep only the latest (like your CP "read until empty; keep last")
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
