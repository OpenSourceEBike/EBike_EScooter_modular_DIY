# main.py — Minimal ESP-NOW + BLE (JBD) coexistence test (optimized)
# - ESP-NOW: sends a tiny packet every 1s with a blinking "brakes" flag
# - BLE: scans and connects to JBD/XiaoXiang BMS using bms_jbd.JbdBmsClient
#
# Notes:
# • BROADCAST_PEER is set to your display MAC. Change if needed.
# • Flip VERBOSE=True while tuning; keep False in production for lowest overhead.

import uasyncio as asyncio
import ubinascii, time
import network
import bluetooth
import espnow

from bms_jbd import JbdBmsClient

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
BROADCAST_PEER = b"\x68\xb6\xb3\x01\xf7\xf3"
BMS_TARGET_NAME = "BMS-FiidoQ1S"

# ESP-NOW blink cadence
BLINK_PERIOD_MS = 1000

# BLE scan/policy
SCAN_BURST_MS   = 3000
REST_GAP_MS     = 2000
BASIC_FRESH_MS  = 2000          # consider BASIC data fresh for 2s
CELLS_EVERY_N_BASIC = 5         # request CELLS every N BASIC frames
PAUSE_CELLS_WHEN_STALE = True

# Logging
VERBOSE = True  # set True to see progress prints; keep False for minimal overhead

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def log(*a):
    if VERBOSE:
        print(*a)

def ticks_now():
    return time.ticks_ms()

def ticks_due(t):
    return time.ticks_diff(ticks_now(), t) >= 0

# ──────────────────────────────────────────────────────────────────────────────
# ESP-NOW setup & task (allocation-light)
# ──────────────────────────────────────────────────────────────────────────────
def espnow_init():
    log("Wi-Fi: enabling STA for ESP-NOW…")
    sta = network.WLAN(network.STA_IF)
    if not sta.active():
        sta.active(True)
    e = espnow.ESPNow()
    e.active(True)
    try:
        e.add_peer(BROADCAST_PEER)
    except OSError:
        pass
    mac = ubinascii.hexlify(sta.config("mac"), b":").decode()
    log("ESP-NOW ready. Our MAC:", mac, "→ peer:", BROADCAST_PEER)
    return e

# Your display expects: "2 0 0 0 0 0 {brakes} 0 0"
# Prebuild both variants to avoid formatting/allocations every second.
PAYLOAD_OFF = b"2 0 0 0 0 0 0 0 0"
PAYLOAD_ON  = b"2 0 0 0 0 0 1 0 0"

async def task_espnow_blink(e):
    brakes_on = 0
    next_toggle = time.ticks_add(ticks_now(), BLINK_PERIOD_MS)
    while True:
        if ticks_due(next_toggle):
            brakes_on ^= 1
            payload = PAYLOAD_ON if brakes_on else PAYLOAD_OFF
            try:
                e.send(BROADCAST_PEER, payload, True)
            except OSError:
                # one short retry on NO_MEM
                await asyncio.sleep_ms(20)
                try:
                    e.send(BROADCAST_PEER, payload, True)
                except OSError:
                    # drop silently to keep timing predictable
                    pass
            next_toggle = time.ticks_add(ticks_now(), BLINK_PERIOD_MS)
            log("Display blink → brakes_on:", bool(brakes_on))
        # small sleep yields to BLE/motor; keep CPU budget tiny
        await asyncio.sleep_ms(5)

# ──────────────────────────────────────────────────────────────────────────────
# Low-duty BLE BMS policy wrapper
# ──────────────────────────────────────────────────────────────────────────────
class LowDutyBms:
    def __init__(self, target=BMS_TARGET_NAME):
        self.ble = bluetooth.BLE()
        self.cli = JbdBmsClient(
            ble=self.ble,
            target_name=target,
            query_period_ms=1000,   # base BASIC cadence; we gate CELLS separately
            poll_delay_ms=250,
            first_kick_ms=200,
            interleave_cells=False, # start BASIC-only; policy will enable CELLS sparsely
            buf_max_bytes=2048,
            debug=True,            # keep quiet for timing
        )
        self._state = 0            # 0=idle,1=scanning,2=connected
        self._basic_ok = False
        self._basic_cnt = 0
        self._next_scan = 0

    def start_scan(self):
        try:
            self.cli.target_name = BMS_TARGET_NAME
            self.cli.start(scan_ms=SCAN_BURST_MS)
            self._state = 1
            log("BLE: scan start for", SCAN_BURST_MS, "ms")
        except OSError as ex:
            # backoff before trying again
            self._next_scan = time.ticks_add(ticks_now(), REST_GAP_MS)
            log("BLE: scan start error:", ex)

    def tick(self):
        # drain notifications / drive state machine; no prints
        self.cli.tick()

    def drive_policy(self):
        if self.cli.is_connected():
            if self._state != 2:
                self._state = 2
                self._basic_ok = False
                self._basic_cnt = 0
                self.cli.interleave_cells = False
                log("BLE: connected")

            # Decide if BASIC is fresh
            fresh = self.cli.is_fresh(BASIC_FRESH_MS)
            if fresh and not self._basic_ok:
                self._basic_ok = True
                log("BLE: BASIC fresh")

            # Pull CELLS sparsely, and pause if BASIC stale
            want_cells = False
            if self._basic_ok and (not (PAUSE_CELLS_WHEN_STALE and not fresh)):
                self._basic_cnt += 1
                if self._basic_cnt >= CELLS_EVERY_N_BASIC:
                    self._basic_cnt = 0
                    want_cells = True

            # toggling this bit lets the client insert an 0x04 request in between BASIC polls
            self.cli.interleave_cells = want_cells
            if want_cells:
                log("BLE: CELLS requested")

        else:
            # Not connected: ensure we scan with a simple backoff
            now = ticks_now()
            if self._state != 1:
                if (self._next_scan == 0) or ticks_due(self._next_scan):
                    self.start_scan()
                else:
                    # idle until next scan window
                    pass

    # quick getters (ints, no float)
    def voltage_x100(self):
        return self.cli.get_battery_voltage_x100()
    def current_x100(self):
        return self.cli.get_current_a_x100()
    def cells_x1000(self):
        return self.cli.get_cells_x1000()
    def is_connected(self):
        return self.cli.is_connected()
    def is_fresh(self, ms=BASIC_FRESH_MS):
        return self.cli.is_fresh(ms)

# ──────────────────────────────────────────────────────────────────────────────
# BLE tasks
# ──────────────────────────────────────────────────────────────────────────────
async def task_bms_driver(lb: LowDutyBms):
    # one-time adapter bring-up (kept outside the hot loop)
    try:
        lb.ble.active(False)
    except:
        pass
    await asyncio.sleep_ms(150)
    lb.ble.active(True)

    # kick off first scan
    lb.start_scan()

    # BLE “tick” fast; policy less often
    last_policy = ticks_now()
    while True:
        lb.tick()
        if time.ticks_diff(ticks_now(), last_policy) >= 200:
            lb.drive_policy()
            last_policy = ticks_now()
        await asyncio.sleep_ms(25)

async def task_bms_reader(lb: LowDutyBms):
    # read cached values periodically; no BLE calls here
    while True:
        if lb.is_connected() and lb.is_fresh(3000):
            ia = lb.current_x100()
            vv = lb.voltage_x100()
            # Avoid floats in steady-state; only log when VERBOSE
            if VERBOSE and (ia is not None) and (vv is not None):
                print("BMS BASIC → I=%d (x100 A), V=%d (x100 V)" % (ia, vv))
            # cells = lb.cells_x1000()  # available if you need it
        await asyncio.sleep_ms(1000)

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    if VERBOSE:
        print("=== Minimal ESP-NOW + BLE BMS coexist test (optimized) ===")

    # ESP-NOW
    e = espnow_init()

    # BLE BMS (low-duty policy wrapper)
    lb = LowDutyBms(target=BMS_TARGET_NAME)

    tasks = [
        asyncio.create_task(task_espnow_blink(e)),
        asyncio.create_task(task_bms_driver(lb)),
        asyncio.create_task(task_bms_reader(lb)),
    ]
    await asyncio.gather(*tasks)

# Kick it off
asyncio.run(main())