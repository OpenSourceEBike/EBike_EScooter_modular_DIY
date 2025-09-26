# bms_jbd.py
# JBD/XiaoXiang BMS (FF00/FF01/FF02) read-only client for MicroPython (ESP32/ESP32-S3)
#
# ──────────────────────────────────────────────────────────────────────────────
# WHAT THIS MODULE DOES
# ──────────────────────────────────────────────────────────────────────────────
# • Discovers a JBD/XiaoXiang BMS over BLE, subscribes to its FF01 characteristic,
#   and periodically “polls” by writing JBD ASCII-like binary command frames to FF02.
# • Caches the most recent BASIC (0x03) and CELLS (0x04) responses and exposes
#   getters such as get_battery_voltage(), get_cells(), get_soc_percent(), etc.
# • Provides a cooperative “tick()” method to run from your main loop. No threads.
#
# ──────────────────────────────────────────────────────────────────────────────
# PROTOCOL PRIMER (JBD “UART” protocol tunneled over BLE)
# ──────────────────────────────────────────────────────────────────────────────
# JBD BMS devices speak a simple framed protocol. Over serial it looks the same,
# but here we tunnel it over BLE GATT:
#
#   READ (host→BMS):  DD A5 <CMD> 00  FF <CHK> 77
#   WRITE(host→BMS):  DD 5A <CMD> LEN_H LEN_L  <DATA...>  <CHK_H> <CHK_L> 77
#
# Fields:
#   • 0xDD         : Start byte
#   • 0xA5 / 0x5A  : Direction (A5 = read request; 5A = write request)
#   • <CMD>        : Verb/function code (0x03 basic info; 0x04 cell voltages; others exist)
#   • LEN          : For reads it’s 0x0000; for writes it’s payload length
#   • <DATA...>    : Optional payload on writes
#   • <CHK> / <CHK_H,CHK_L>:
#       16-bit checksum computed as: take the sum of all bytes from the 0xDD
#       (inclusive) up to (but not including) the checksum; then CHK = (0x10000 - sum) & 0xFFFF
#   • 0x77         : Frame terminator
#
# RESPONSE (BMS→host, to FF01 “notify” or when we read FF01):
#   DD <CMD> LEN_H LEN_L <DATA...> <CHK_H> <CHK_L> 77
#
# Notes:
# • For “read” requests (like 0x03, 0x04), the host writes the READ frame to FF02.
#   The BMS replies by NOTIFYing a single response frame on FF01.
# • We do not do blocking reads. We only write a request and then drain
#   notifications in our tick() loop. This is resilient on BLE and avoids
#   synchronous stalls.
#
# ──────────────────────────────────────────────────────────────────────────────
# WHAT WE PARSE
# ──────────────────────────────────────────────────────────────────────────────
# • 0x03 (BASIC): total voltage, current, SoC, cycle count, remaining/full capacity,
#   MOSFET flags, NTC temps, protection bits, balancing bitmap, etc.
# • 0x04 (CELLS): per-cell voltages in millivolts.
#
# Different firmware variants can rearrange some reserved bytes; we tolerate that
# by checksum-validating and only reading the fields we know and bounds-checking.
#
# ──────────────────────────────────────────────────────────────────────────────
# BUFFERING STRATEGY
# ──────────────────────────────────────────────────────────────────────────────
# BLE notifications can split frames arbitrarily (or batch multiple frames).
# We therefore maintain a bytearray “ring” with a moving head index (_head).
# • push: append new bytes
# • pop_frame: search for 0xDD, compute expected total length from LEN field,
#   return a complete frame if present; otherwise leave bytes buffered
# • Compact occasionally to keep memory small without expensive per-byte deletes
#
# This is optimized for MicroPython heap constraints and avoids slicing churn.
#
# ──────────────────────────────────────────────────────────────────────────────
# SCHEDULER
# ──────────────────────────────────────────────────────────────────────────────
# The JbdBmsClient is event-driven by BLE IRQs for discovery/notification,
# and time-driven by “tick()” which:
# • drains any assembled frames and updates the cache,
# • sends the next “read” request (0x03 or 0x04) when due,
# • backs off if we’re waiting for a response,
# • re-kicks polls if nothing arrived for a while.
#
# You should call tick() every 50–200 ms from your main loop.
#
# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────
#   bms = JbdBmsClient(target_name="BMS-BTT_JP")
#   bms.start()
#   while True:
#       bms.tick()
#       if bms.is_connected() and bms.is_fresh(3000):
#           v = bms.get_battery_voltage()
#           cells = bms.get_cells()
#           ...
#
# See the companion main.py for a small example. (Your current main.py already
# uses this shape.)  The getters return None until the first valid frame arrives.
#
# ──────────────────────────────────────────────────────────────────────────────

import bluetooth, time
from micropython import const

# ===== BLE IRQ constants =====
# MicroPython raises BLE IRQs for scanning, connection, GATT discovery, etc.
# We only do light work in the IRQ handler; heavy/parsing is done in tick().
_IRQ_SCAN_RESULT                 = const(5)
_IRQ_SCAN_DONE                   = const(6)
_IRQ_PERIPHERAL_CONNECT          = const(7)
_IRQ_PERIPHERAL_DISCONNECT       = const(8)
_IRQ_GATTC_SERVICE_RESULT        = const(9)
_IRQ_GATTC_SERVICE_DONE          = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE   = const(12)
_IRQ_GATTC_DESCRIPTOR_RESULT     = const(13)
_IRQ_GATTC_DESCRIPTOR_DONE       = const(14)
_IRQ_GATTC_NOTIFY                = const(18)

# ===== BLE UUIDs exposed by JBD over GATT =====
# FF00: Service
# FF01: Characteristic for “data out” (notify/read)
# FF02: Characteristic for “data in”  (write)
SVC_UUID    = bluetooth.UUID(0xFF00)
NOTIFY_UUID = bluetooth.UUID(0xFF01)
WRITE_UUID  = bluetooth.UUID(0xFF02)
CCCD_UUID   = bluetooth.UUID(0x2902)    # Standard Client Characteristic Config

# ===== JBD “READ” commands (host→BMS via FF02) =====
# Only these are used here (read-only). The BMS answers on FF01.
CMD_BASIC = bytes([0xDD,0xA5,0x03,0x00,0xFF,0xFD,0x77])  # Query BASIC info (voltage/current/SoC/temps/…)
CMD_CELLS = bytes([0xDD,0xA5,0x04,0x00,0xFF,0xFC,0x77])  # Query per-cell voltages

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: fixed-width integers and protection/bitmap decoding
# ──────────────────────────────────────────────────────────────────────────────

def _s16(msb, lsb):
    """Signed 16-bit big-endian to Python int."""
    v = ((msb << 8) | lsb) & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v

def _u16(msb, lsb):
    """Unsigned 16-bit big-endian to Python int."""
    return ((msb << 8) | lsb) & 0xFFFF

def _decode_prod_date(val):
    """JBD encodes production date as: y:7bits (offset 2000), m:4bits, d:5bits."""
    y = 2000 + ((val >> 9) & 0x7F)
    m = (val >> 5) & 0x0F
    d = val & 0x1F
    return (y, m, d)

def _recognized_protections(bits):
    """
    Maps lower 12 bits to human labels (varies by fw; this set is common).
    """
    labels = [
        (0,  "Cell overvoltage"),
        (1,  "Cell undervoltage"),
        (2,  "Pack overvoltage"),
        (3,  "Pack undervoltage"),
        (4,  "Charge overcurrent"),
        (5,  "Discharge overcurrent"),
        (6,  "Short circuit"),
        (7,  "AFE/IC error"),
        (8,  "Overtemp (chg)"),
        (9,  "Low temp (chg)"),
        (10, "Overtemp (dsg)"),
        (11, "Low temp (dsg)"),
    ]
    out = []
    for b, name in labels:
        if bits & (1 << b):
            out.append(name)
    return out

def _balance_cells_from_bitmap(bal_bytes, cells):
    """
    JBD returns a small bitmap (LSB=cell1) indicating which cells are balancing.
    We expose it as a 1-based list of cell indexes.
    """
    out = []
    mask = 0
    for i in range(min(4, len(bal_bytes))):
        mask |= (bal_bytes[i] & 0xFF) << (8 * i)
    for i in range(cells):
        if mask & (1 << i):
            out.append(i + 1)
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────────────────────────────────────

class JbdBmsClient:
    """
    Read-only BLE client for JBD/XiaoXiang BMS.

    Lifecycle:
      1) start()    : begin scan/connect (non-blocking)
      2) tick()     : call often to process notifications and schedule polls
      3) getters    : read cached, last-known data
      4) is_connected() / is_fresh() : determine whether data can be trusted

    Design choices:
      • No busy waits; we only send read-requests and consume FF01 notifications.
      • A lightweight scheduler in tick() sequences requests and retries.
      • A compact parsing pipeline accepts frames even if a few leading bytes
        are noisy; checksum validation ensures correctness.
    """

    def __init__(
        self,
        ble=None,
        target_name="BMS-BTT_JP",
        query_period_ms=1000,
        poll_delay_ms=300,
        first_kick_ms=250,
        interleave_cells=True,      # True: alternate 0x03 and 0x04; False: basic only
        buf_max_bytes=4096,
        debug=False,
    ):
        # BLE setup: single central client instance and IRQ hook
        self.ble = ble or bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        # Configuration knobs
        self.target_name = target_name
        self.query_period_ms = query_period_ms
        self.poll_delay_ms = poll_delay_ms
        self.first_kick_ms = first_kick_ms
        self.interleave_cells = interleave_cells
        self.buf_max_bytes = buf_max_bytes
        self.debug = bool(debug)

        # GATT discovery results (filled from IRQs)
        self.conn = None          # connection handle
        self.srange = None        # (start,end) of FF00 service
        self.h_n = None           # value handle for FF01 (notify/read)
        self.h_w = None           # value handle for FF02 (write)
        self.h_cccd = None        # descriptor handle for FF01 CCCD

        # Polling scheduler state
        self.next_ms = 0          # when to do the next step
        self.awaiting = False     # True after we wrote a read-request
        self.phase = 0            # toggles between 0x03 and 0x04 when interleave_cells=True
        self.last_data_ms = 0     # last time any valid frame arrived

        # Frame buffer (head pointer = _head; no per-byte deletes)
        self._buf = bytearray()
        self._head = 0

        # Cached last-known data
        self._last_basic = None   # dict with pack info
        self._last_cells = None   # list[float] per-cell volts

    # ───────── Public API ─────────

    def start(self, scan_ms=8000):
        """Begin scanning for the BMS; non-blocking; results delivered via IRQ."""
        self._scan(scan_ms)

    def stop(self):
        """Stop scanning and disconnect if connected; clears state."""
        try:
            self.ble.gap_scan(None)
        except:
            pass
        try:
            if self.conn is not None:
                self.ble.gap_disconnect(self.conn)
        except:
            pass
        self._reset_state(clear_buf=True)

    def tick(self):
        """
        Cooperative heartbeat:
          • drains and parses any complete frames in the buffer,
          • sequences read polls (0x03 / 0x04),
          • re-kicks if notifications stall.
        Call this periodically in your main loop (50–200 ms is plenty).
        """
        try:
            # 1) Parse whatever the IRQ has pushed so far (from FF01 notifies)
            self._drain_frames()

            # If we’re not yet connected or haven’t found FF01, there’s nothing to do
            if (self.conn is None) or (self.h_n is None):
                return

            t = time.ticks_ms()

            # 2) Poll scheduler:
            #    We alternate: write CMD_BASIC → wait a short POLL_DELAY → (optionally) write CMD_CELLS → …
            if self.next_ms and time.ticks_diff(t, self.next_ms) >= 0:
                self.next_ms = 0
                if (not self.awaiting) and (self.h_w is not None):
                    # Decide which command to send this cycle
                    payload = CMD_BASIC if (not self.interleave_cells or self.phase == 0) else CMD_CELLS
                    self._write(payload)            # write to FF02
                    self.awaiting = True            # expect a notify soon
                    self.next_ms = time.ticks_add(t, self.poll_delay_ms)
                    if self.interleave_cells:
                        self.phase ^= 1
                elif self.awaiting:
                    # Didn’t see a notify within poll_delay_ms; don’t hammer the bus.
                    # Back off until the next full period and try again.
                    self.awaiting = False
                    self.next_ms = time.ticks_add(time.ticks_ms(), self.query_period_ms)

            # 3) Idle re-kick in case we’ve gone quiet for 3× the period
            if self.last_data_ms and time.ticks_diff(t, self.last_data_ms) > (self.query_period_ms * 3) and (not self.awaiting):
                self._schedule_send(100)

        except Exception as ex:
            if self.debug:
                print("tick exception:", ex)

    # Connection/data health

    def is_connected(self):
        """True if BLE link is up AND we discovered FF01 (notify) handle."""
        return (self.conn is not None) and (self.h_n is not None)

    def is_fresh(self, max_age_ms=3000):
        """True if we received any data within the given time budget."""
        if not self.last_data_ms:
            return False
        return time.ticks_diff(time.ticks_ms(), self.last_data_ms) <= max_age_ms

    # ───────── Getters for last-known values (None if not yet known) ─────────

    def get_battery_voltage(self):
        d = self._last_basic
        return d["voltage_v"] if d else None

    def get_current_a(self):
        d = self._last_basic
        return d["current_a"] if d else None

    def get_soc_percent(self):
        d = self._last_basic
        return d["soc_pct"] if d else None

    def get_cycle_count(self):
        d = self._last_basic
        return d["cycle_cnt"] if d else None

    def get_capacities_ah(self):
        """Returns (remaining_ah, full_ah) or None."""
        d = self._last_basic
        if not d:
            return None
        return (d["cap_rem_ah"], d["cap_full_ah"])

    def get_mosfets(self):
        """Returns (chg_on, dsg_on) as booleans or None."""
        d = self._last_basic
        if not d:
            return None
        return (bool(d["fet_chg"]), bool(d["fet_dsg"]))

    def get_cells(self):
        """Returns list[float] of cell voltages, or None."""
        return self._last_cells

    def get_temps_c(self):
        """Returns list[float] of NTC temps in °C, or None."""
        d = self._last_basic
        return d["temps_c"] if d else None

    def get_protections(self):
        """Returns list[str] of active protections (empty if none)."""
        d = self._last_basic
        return d["prot_list"] if d else []

    def get_balancing_cells(self):
        """Returns 1-based indexes of cells that are balancing (empty if none)."""
        d = self._last_basic
        return d["balance_cells"] if d else []

    def get_last_update_ms(self):
        """ticks_ms() timestamp when we last stored any valid frame."""
        return self.last_data_ms

    # ───────── Internals: BLE + scheduling + buffering + parsing ─────────

    # Scanning & connection orchestration

    def _scan(self, ms):
        if self.debug:
            print("Scanning…")
        try:
            # (window, interval) are large to be power-friendly for a central
            self.ble.gap_scan(ms, 30000, 30000)
        except Exception as ex:
            if self.debug:
                print("gap_scan error:", ex)

    def _reset_state(self, clear_buf=False):
        # Reset everything except the BLE stack itself
        self.conn = None
        self.srange = None
        self.h_n = None
        self.h_w = None
        self.h_cccd = None
        self.next_ms = 0
        self.awaiting = False
        self.phase = 0
        self.last_data_ms = 0
        if clear_buf:
            self._buf = bytearray()
            self._head = 0

    def _schedule_send(self, delay_ms):
        # Arm the scheduler to perform a step after delay_ms
        self.next_ms = time.ticks_add(time.ticks_ms(), delay_ms)
        self.awaiting = False

    # Buffering/framing (single grow-only bytearray with moving head)

    def _buf_clear(self):
        self._buf = bytearray()
        self._head = 0

    def _maybe_compact(self, force=False):
        # Occasionally compact to drop already-consumed bytes without per-byte deletes
        if self._head and (force or self._head > 1024 or self._head > (len(self._buf) >> 1)):
            self._buf = self._buf[self._head:]
            self._head = 0

    def _push_bytes(self, chunk):
        # Append new incoming bytes; drop oldest if > buf_max_bytes
        if not chunk:
            return
        unread = len(self._buf) - self._head
        total_after = unread + len(chunk)
        if total_after > self.buf_max_bytes:
            drop = total_after - self.buf_max_bytes
            if drop >= unread:
                self._buf_clear()
            else:
                self._head += drop
                self._maybe_compact()
        self._buf.extend(chunk)

    def _pop_frame(self):
        """
        Try to extract exactly one complete JBD frame:
          DD … LEN_H LEN_L … <CHK_H><CHK_L> 77
        Strategy:
          • scan for 0xDD,
          • compute total length from LEN,
          • if enough bytes present and terminator 0x77 matches, return that slice.
        """
        while True:
            n = len(self._buf) - self._head
            if n < 5:
                return None
            mv = memoryview(self._buf)[self._head:]
            # Find next potential start (0xDD)
            j = 0
            while j < n and mv[j] != 0xDD:
                j += 1
            if j >= n:
                # If buffer is bloated with junk, clear; otherwise leave it
                if len(self._buf) > 64:
                    self._buf_clear()
                return None
            if j:
                # Skip any junk before 0xDD
                self._head += j
                self._maybe_compact()
                n = len(self._buf) - self._head
                if n < 5:
                    return None
                mv = memoryview(self._buf)[self._head:]
            # Expected data length from header bytes [2],[3]
            ln = (mv[2] << 8) | mv[3]
            total = 1 + 1 + 2 + ln + 2 + 1  # DD + CMD + LEN(2) + DATA + CHK(2) + 77
            # Sanity: disallow absurd totals to avoid lockups
            if total <= 0 or total > self.buf_max_bytes:
                self._head += 1
                self._maybe_compact()
                continue
            if n < total:
                # Not enough yet—wait for more bytes
                return None
            # Candidate frame slice
            f = bytes(mv[:total])
            self._head += total
            self._maybe_compact()
            # Accept only if trailing 0x77 present; otherwise resync by one byte
            if f[-1] == 0x77:
                return f
            self._head += 1
            self._maybe_compact()

    # CRC/validation and parsers

    def _frame_ok(self, f):
        """
        Validate by checksum. Some firmwares are finicky with which prefix is
        included in the sum; we allow a few plausible start offsets (0..3) and
        end positions (len-3 or len-4) to tolerate edge conditions while still
        guaranteeing the final 16-bit sum matches the received checksum.
        """
        if (not f) or (len(f) < 7) or (f[0] != 0xDD) or (f[-1] != 0x77):
            return False
        recv = (f[-3] << 8) | f[-2]
        n = len(f)

        def ok(start, end_excl):
            if end_excl <= start:
                return False
            s = 0
            for b in f[start:end_excl]:
                s = (s + b) & 0xFFFF
            calc = (0x10000 - s) & 0xFFFF
            return calc == recv

        for st in (0, 1, 2, 3):
            for en in (n - 3, n - 4):
                if ok(st, en):
                    return True
        return False

    def _parse_basic(self, f):
        """
        Parse 0x03 BASIC frame into a dict with:
          voltage_v, current_a, soc_pct, cycle_cnt, cap_rem_ah, cap_full_ah,
          fet_chg/fet_dsg (0/1), temps_c (list), prot_list (list[str]),
          balance_cells (list[int]), cells (cell count)
        """
        if (not self._frame_ok(f)) or (f[1] != 0x03):
            return None
        d = f[4:-3]                 # strip DD CMD LEN(2) …. CHK(2) 77
        if len(d) < 23:
            return None

        voltage_v   = ((d[0] << 8) | d[1]) / 100.0
        current_a   = _s16(d[2], d[3]) / 100.0
        cap_rem_ah  = _u16(d[4], d[5]) / 100.0
        cap_full_ah = _u16(d[6], d[7]) / 100.0
        cycle_cnt   = _u16(d[8], d[9])
        prod_date   = _u16(d[10], d[11])         # (y,m,d) available if needed
        bal_bytes   = d[12:16]                   # cell-balance bitmap
        # Byte layout varies across firmwares; [16:18] is protections on common variants
        prot_bits   = _u16(d[16], d[17])
        # d[18] is sometimes version byte; we ignore it for portability
        soc_pct     = d[19]
        fet_flags   = d[20]                      # bit0=CHG, bit1=DSG
        cells       = d[21]                      # cell count
        ntc_count   = d[22]                      # number of NTC temps that follow

        # NTC temperatures: each as tenths of Kelvin; convert to °C as (raw/10 - 273.1)
        temps = []
        off = 23
        for _ in range(ntc_count):
            if off + 1 >= len(d):
                break
            raw = _u16(d[off], d[off + 1])
            temps.append((raw / 10.0) - 273.1)
            off += 2

        y, m, day = _decode_prod_date(prod_date)
        prot_list = _recognized_protections(prot_bits)
        fet_chg   = 1 if (fet_flags & 0x01) else 0
        fet_dsg   = 1 if (fet_flags & 0x02) else 0
        balancing = _balance_cells_from_bitmap(bal_bytes, cells)

        return {
            "voltage_v": voltage_v,
            "current_a": current_a,
            "soc_pct": soc_pct,
            "fet_chg": fet_chg,
            "fet_dsg": fet_dsg,
            "cycle_cnt": cycle_cnt,
            "cap_rem_ah": cap_rem_ah,
            "cap_full_ah": cap_full_ah,
            "prod_date": (y, m, day),
            "prot_list": prot_list,
            "cells": cells,
            "temps_c": temps,
            "balance_cells": balancing,
        }

    def _parse_cells(self, f):
        """Parse 0x04 CELLS frame into a list of per-cell voltages (float, volts)."""
        if (not self._frame_ok(f)) or (f[1] != 0x04):
            return None
        d = f[4:-3]
        out = []
        i = 0
        n = len(d)
        while i + 1 < n:
            mv = (d[i] << 8) | d[i + 1]   # mV
            if 0 < mv < 6000:
                out.append(mv / 1000.0)  # V
            i += 2
        return out or None

    # BLE write helper (to FF02)

    def _write(self, payload):
        """
        Try “Write No Response” first (fast), fallback to “Write With Response”
        if the adapter rejects WNR. We do not block waiting for a response.
        """
        try:
            self.ble.gattc_write(self.conn, self.h_w, payload, 0)  # WNR
        except:
            try:
                self.ble.gattc_write(self.conn, self.h_w, payload, 1)  # With RSP
            except:
                pass

    # Drain any complete frames into the data cache; invoke callbacks if present.

    def _drain_frames(self):
        changed = False
        while True:
            f = self._pop_frame()
            if not f:
                break
            cmd = f[1]
            if cmd == 0x03:
                info = self._parse_basic(f)
                if info:
                    self._last_basic = info
                    self.last_data_ms = time.ticks_ms()
                    changed = True
            elif cmd == 0x04 and self.interleave_cells:
                cells = self._parse_cells(f)
                if cells:
                    self._last_cells = cells
                    self.last_data_ms = time.ticks_ms()
                    changed = True
        return changed

    # BLE IRQ handler: do only small/quick operations here.

    def _irq(self, e, d):
        try:
            if e == _IRQ_SCAN_RESULT:
                # We only care about advertisements from our target_name; once seen,
                # stop scanning and initiate a connection.
                at, addr, atype, rssi, adv = d
                nm = None
                i = 0; adv = bytes(adv); n = len(adv)
                while i + 1 < n:
                    L = adv[i]
                    if L == 0: break
                    t = adv[i+1]
                    p = adv[i+2:i+1+L]
                    if t in (0x09, 0x08):         # Complete/Shortened Local Name
                        try: nm = p.decode("utf-8")
                        except: nm = bytes(p).decode("utf-8", "ignore")
                        break
                    i += 1 + L
                if nm == self.target_name:
                    self.ble.gap_scan(None)
                    self.ble.gap_connect(at, addr)

            elif e == _IRQ_PERIPHERAL_CONNECT:
                # Begin service discovery for FF00 on connect
                self.conn, _, _ = d
                self.ble.gattc_discover_services(self.conn)

            elif e == _IRQ_GATTC_SERVICE_RESULT:
                # Capture FF00 service range for later characteristic discovery
                ch, start, end, uuid = d
                if ch == self.conn and uuid == SVC_UUID:
                    self.srange = (start, end)

            elif e == _IRQ_GATTC_SERVICE_DONE:
                # Move on to characteristic discovery (FF01/FF02)
                if self.srange:
                    s, e2 = self.srange
                    self.ble.gattc_discover_characteristics(self.conn, s, e2)
                else:
                    self._reset_state()
                    self._scan(8000)

            elif e == _IRQ_GATTC_CHARACTERISTIC_RESULT:
                # Record handles for notify (FF01) and write (FF02)
                ch, _, val_h, props, uuid = d
                if ch != self.conn:
                    return
                if uuid == NOTIFY_UUID:
                    self.h_n = val_h
                elif uuid == WRITE_UUID:
                    self.h_w = val_h

            elif e == _IRQ_GATTC_CHARACTERISTIC_DONE:
                # Discover and enable notifications on FF01 (write CCCD)
                if self.h_n is not None:
                    self.ble.gattc_discover_descriptors(self.conn, self.h_n, self.h_n + 3)
                    self._schedule_send(self.first_kick_ms)   # first poll
                else:
                    self._reset_state()
                    self._scan(8000)

            elif e == _IRQ_GATTC_DESCRIPTOR_RESULT:
                # Find CCCD handle (FF01 + 1)
                ch, dh, duuid = d
                if ch == self.conn and duuid == CCCD_UUID and dh == (self.h_n + 1):
                    self.h_cccd = dh

            elif e == _IRQ_GATTC_DESCRIPTOR_DONE:
                # Enable notifications (0x0001) if CCCD is present
                if self.h_cccd:
                    try:
                        self.ble.gattc_write(self.conn, self.h_cccd, b"\x01\x00", 1)
                    except:
                        pass

            elif e == _IRQ_GATTC_NOTIFY:
                # Append notify payload to our buffer; tick() will parse it
                ch, vh, nd = d
                if ch == self.conn and vh == self.h_n:
                    self._push_bytes(bytes(nd))
                    self.awaiting = False
                    self.last_data_ms = time.ticks_ms()

            elif e == _IRQ_PERIPHERAL_DISCONNECT:
                # Auto-reconnect: clear state and restart scanning
                ch, _, _ = d
                if ch == self.conn:
                    self._reset_state()
                    self._scan(8000)
        except:
            # Keep IRQ handler resilient; any exception here would crash the BLE loop
            pass
