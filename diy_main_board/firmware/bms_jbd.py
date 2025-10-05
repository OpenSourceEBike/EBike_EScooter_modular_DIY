# bms_jbd.py
# JBD/XiaoXiang BMS (FF00/FF01/FF02) read-only client for MicroPython (ESP32/ESP32-S3)
#
# Scales:
#   - Pack/Current/Capacity/Temps are returned as ×100 integers (…_x100).
#   - Per-cell voltages are returned as ×1000 integers (millivolts) via get_cells_x1000().

import bluetooth, time
from micropython import const

# ===== BLE IRQ constants =====
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
SVC_UUID    = bluetooth.UUID(0xFF00)
NOTIFY_UUID = bluetooth.UUID(0xFF01)
WRITE_UUID  = bluetooth.UUID(0xFF02)
CCCD_UUID   = bluetooth.UUID(0x2902)

# ===== JBD “READ” commands (host→BMS via FF02) =====
CMD_BASIC = bytes([0xDD,0xA5,0x03,0x00,0xFF,0xFD,0x77])  # BASIC info
CMD_CELLS = bytes([0xDD,0xA5,0x04,0x00,0xFF,0xFC,0x77])  # per-cell mV

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _s16(msb, lsb):
    v = ((msb << 8) | lsb) & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v

def _u16(msb, lsb):
    return ((msb << 8) | lsb) & 0xFFFF

def _decode_prod_date(val):
    y = 2000 + ((val >> 9) & 0x7F)
    m = (val >> 5) & 0x0F
    d = val & 0x1F
    return (y, m, d)

def _recognized_protections(bits):
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

    Integer scales:
      - voltage_v_x100        (V×100)
      - current_a_x100        (A×100, signed)
      - cap_rem_ah_x100       (Ah×100)
      - cap_full_ah_x100      (Ah×100)
      - temps_c_x100[]        (°C×100)
      - get_cells_x1000()     -> list of per-cell voltages in V×1000 (mV)

    Unchanged:
      - soc_pct (0..100), cycle_cnt, fet flags, protections list, balancing cells.
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
        self.ble = ble or bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.target_name = target_name
        self.query_period_ms = query_period_ms
        self.poll_delay_ms = poll_delay_ms
        self.first_kick_ms = first_kick_ms
        self.interleave_cells = interleave_cells
        self.buf_max_bytes = buf_max_bytes
        self.debug = bool(debug)

        self.conn = None
        self.srange = None
        self.h_n = None
        self.h_w = None
        self.h_cccd = None

        self.next_ms = 0
        self.awaiting = False
        self.phase = 0
        self.last_data_ms = 0

        self._buf = bytearray()
        self._head = 0

        # Cached last-known data
        self._last_basic = None        # dict with *_x100 fields + others unchanged
        self._last_cells_x1000 = None  # list[int] of per-cell V×1000 (mV)

    # ───────── Public API ─────────

    def start(self, scan_ms=8000):
        self._scan(scan_ms)

    def stop(self):
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
        try:
            self._drain_frames()

            if (self.conn is None) or (self.h_n is None):
                return

            t = time.ticks_ms()

            if self.next_ms and time.ticks_diff(t, self.next_ms) >= 0:
                self.next_ms = 0
                if (not self.awaiting) and (self.h_w is not None):
                    payload = CMD_BASIC if (not self.interleave_cells or self.phase == 0) else CMD_CELLS
                    self._write(payload)
                    self.awaiting = True
                    self.next_ms = time.ticks_add(t, self.poll_delay_ms)
                    if self.interleave_cells:
                        self.phase ^= 1
                elif self.awaiting:
                    self.awaiting = False
                    self.next_ms = time.ticks_add(time.ticks_ms(), self.query_period_ms)

            if self.last_data_ms and time.ticks_diff(t, self.last_data_ms) > (self.query_period_ms * 3) and (not self.awaiting):
                self._schedule_send(100)

        except Exception as ex:
            if self.debug:
                print("tick exception:", ex)

    # Connection/data health

    def is_connected(self):
        return (self.conn is not None) and (self.h_n is not None)

    def is_fresh(self, max_age_ms=3000):
        if not self.last_data_ms:
            return False
        return time.ticks_diff(time.ticks_ms(), self.last_data_ms) <= max_age_ms

    # ───────── Getters (×100 or ×1000 where applicable) ─────────

    def get_battery_voltage_x100(self):
        d = self._last_basic
        return d["voltage_v_x100"] if d else None

    def get_current_a_x100(self):
        d = self._last_basic
        return d["current_a_x100"] if d else None

    def get_soc_percent(self):
        d = self._last_basic
        return d["soc_pct"] if d else None

    def get_cycle_count(self):
        d = self._last_basic
        return d["cycle_cnt"] if d else None

    def get_capacities_ah_x100(self):
        """Returns (remaining_ah_x100, full_ah_x100) or None."""
        d = self._last_basic
        if not d:
            return None
        return (d["cap_rem_ah_x100"], d["cap_full_ah_x100"])

    def get_mosfets(self):
        """Returns (chg_on, dsg_on) as booleans or None."""
        d = self._last_basic
        if not d:
            return None
        return (bool(d["fet_chg"]), bool(d["fet_dsg"]))

    def get_cells_x1000(self):
        """Returns list[int] of per-cell voltages in V×1000 (millivolts), or None."""
        return self._last_cells_x1000

    def get_temps_c_x100(self):
        """Returns list[int] of NTC temps in °C×100, or None."""
        d = self._last_basic
        return d["temps_c_x100"] if d else None

    def get_protections(self):
        d = self._last_basic
        return d["prot_list"] if d else []

    def get_balancing_cells(self):
        d = self._last_basic
        return d["balance_cells"] if d else []

    def get_last_update_ms(self):
        return self.last_data_ms

    # ───────── Internals: BLE + scheduling + buffering + parsing ─────────

    def _scan(self, ms):
        if self.debug:
            print("Scanning…")
        try:
            self.ble.gap_scan(ms, 30000, 30000)
        except Exception as ex:
            if self.debug:
                print("gap_scan error:", ex)

    def _reset_state(self, clear_buf=False):
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
        self.next_ms = time.ticks_add(time.ticks_ms(), delay_ms)
        self.awaiting = False

    # Buffering/framing

    def _buf_clear(self):
        self._buf = bytearray()
        self._head = 0

    def _maybe_compact(self, force=False):
        if self._head and (force or self._head > 1024 or self._head > (len(self._buf) >> 1)):
            self._buf = self._buf[self._head:]
            self._head = 0

    def _push_bytes(self, chunk):
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
        while True:
            n = len(self._buf) - self._head
            if n < 5:
                return None
            mv = memoryview(self._buf)[self._head:]
            j = 0
            while j < n and mv[j] != 0xDD:
                j += 1
            if j >= n:
                if len(self._buf) > 64:
                    self._buf_clear()
                return None
            if j:
                self._head += j
                self._maybe_compact()
                n = len(self._buf) - self._head
                if n < 5:
                    return None
                mv = memoryview(self._buf)[self._head:]
            ln = (mv[2] << 8) | mv[3]
            total = 1 + 1 + 2 + ln + 2 + 1
            if total <= 0 or total > self.buf_max_bytes:
                self._head += 1
                self._maybe_compact()
                continue
            if n < total:
                return None
            f = bytes(mv[:total])
            self._head += total
            self._maybe_compact()
            if f[-1] == 0x77:
                return f
            self._head += 1
            self._maybe_compact()

    def _frame_ok(self, f):
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
        Parse 0x03 BASIC frame into a dict with *_x100 fields where applicable:
          voltage_v_x100, current_a_x100, cap_rem_ah_x100, cap_full_ah_x100,
          soc_pct, cycle_cnt, fet_chg, fet_dsg, temps_c_x100[], prot_list,
          balance_cells[], cells
        """
        if (not self._frame_ok(f)) or (f[1] != 0x03):
            return None
        d = f[4:-3]
        if len(d) < 23:
            return None

        voltage_v_x100   = _u16(d[0], d[1])        # V×100
        current_a_x100   = _s16(d[2], d[3])        # A×100 (signed)
        cap_rem_ah_x100  = _u16(d[4], d[5])        # Ah×100
        cap_full_ah_x100 = _u16(d[6], d[7])        # Ah×100
        cycle_cnt        = _u16(d[8], d[9])
        prod_date        = _u16(d[10], d[11])
        bal_bytes        = d[12:16]
        prot_bits        = _u16(d[16], d[17])
        soc_pct          = d[19]                   # 0..100
        fet_flags        = d[20]                   # bit0=CHG, bit1=DSG
        cells            = d[21]
        ntc_count        = d[22]

        # NTC temps: raw in 0.1 K; °C×100 = raw*10 - 27310
        temps_c_x100 = []
        off = 23
        for _ in range(ntc_count):
            if off + 1 >= len(d):
                break
            raw = _u16(d[off], d[off + 1])  # 0.1 K
            temps_c_x100.append((raw * 10) - 27310)
            off += 2

        y, m, day = _decode_prod_date(prod_date)
        prot_list = _recognized_protections(prot_bits)
        fet_chg   = 1 if (fet_flags & 0x01) else 0
        fet_dsg   = 1 if (fet_flags & 0x02) else 0
        balancing = _balance_cells_from_bitmap(bal_bytes, cells)

        return {
            "voltage_v_x100": voltage_v_x100,
            "current_a_x100": current_a_x100,
            "soc_pct": soc_pct,
            "fet_chg": fet_chg,
            "fet_dsg": fet_dsg,
            "cycle_cnt": cycle_cnt,
            "cap_rem_ah_x100": cap_rem_ah_x100,
            "cap_full_ah_x100": cap_full_ah_x100,
            "prod_date": (y, m, day),
            "prot_list": prot_list,
            "cells": cells,
            "temps_c_x100": temps_c_x100,
            "balance_cells": balancing,
        }

    def _parse_cells(self, f):
        """
        Parse 0x04 CELLS frame into list of per-cell voltages in V×1000 (ints).
        JBD provides mV per cell; return raw mV (no division).
        """
        if (not self._frame_ok(f)) or (f[1] != 0x04):
            return None
        d = f[4:-3]
        out = []
        i = 0
        n = len(d)
        while i + 1 < n:
            mv = (d[i] << 8) | d[i + 1]   # mV
            if 0 < mv < 6000:
                out.append(mv)            # V×1000 (raw mV)
            i += 2
        return out or None

    def _write(self, payload):
        try:
            self.ble.gattc_write(self.conn, self.h_w, payload, 0)  # WNR
        except:
            try:
                self.ble.gattc_write(self.conn, self.h_w, payload, 1)  # With RSP
            except:
                pass

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
                cells_x1000 = self._parse_cells(f)
                if cells_x1000:
                    self._last_cells_x1000 = cells_x1000
                    self.last_data_ms = time.ticks_ms()
                    changed = True
        return changed

    # BLE IRQ handler

    def _irq(self, e, d):
        try:
            if e == _IRQ_SCAN_RESULT:
                at, addr, atype, rssi, adv = d
                nm = None
                i = 0; adv = bytes(adv); n = len(adv)
                while i + 1 < n:
                    L = adv[i]
                    if L == 0: break
                    t = adv[i+1]
                    p = adv[i+2:i+1+L]
                    if t in (0x09, 0x08):
                        try: nm = p.decode("utf-8")
                        except: nm = bytes(p).decode("utf-8", "ignore")
                        break
                    i += 1 + L
                if nm == self.target_name:
                    self.ble.gap_scan(None)
                    self.ble.gap_connect(at, addr)

            elif e == _IRQ_PERIPHERAL_CONNECT:
                self.conn, _, _ = d
                self.ble.gattc_discover_services(self.conn)

            elif e == _IRQ_GATTC_SERVICE_RESULT:
                ch, start, end, uuid = d
                if ch == self.conn and uuid == SVC_UUID:
                    self.srange = (start, end)

            elif e == _IRQ_GATTC_SERVICE_DONE:
                if self.srange:
                    s, e2 = self.srange
                    self.ble.gattc_discover_characteristics(self.conn, s, e2)
                else:
                    self._reset_state()
                    self._scan(8000)

            elif e == _IRQ_GATTC_CHARACTERISTIC_RESULT:
                ch, _, val_h, props, uuid = d
                if ch != self.conn:
                    return
                if uuid == NOTIFY_UUID:
                    self.h_n = val_h
                elif uuid == WRITE_UUID:
                    self.h_w = val_h

            elif e == _IRQ_GATTC_CHARACTERISTIC_DONE:
                if self.h_n is not None:
                    self.ble.gattc_discover_descriptors(self.conn, self.h_n, self.h_n + 3)
                    self._schedule_send(self.first_kick_ms)
                else:
                    self._reset_state()
                    self._scan(8000)

            elif e == _IRQ_GATTC_DESCRIPTOR_RESULT:
                ch, dh, duuid = d
                if ch == self.conn and duuid == CCCD_UUID and dh == (self.h_n + 1):
                    self.h_cccd = dh

            elif e == _IRQ_GATTC_DESCRIPTOR_DONE:
                if self.h_cccd:
                    try:
                        self.ble.gattc_write(self.conn, self.h_cccd, b"\x01\x00", 1)
                    except:
                        pass

            elif e == _IRQ_GATTC_NOTIFY:
                ch, vh, nd = d
                if ch == self.conn and vh == self.h_n:
                    self._push_bytes(bytes(nd))
                    self.awaiting = False
                    self.last_data_ms = time.ticks_ms()

            elif e == _IRQ_PERIPHERAL_DISCONNECT:
                ch, _, _ = d
                if ch == self.conn:
                    self._reset_state()
                    self._scan(8000)
        except:
            pass
