# MicroPython — ESP32/ESP32-S3 JBD/XiaoXiang BMS (FF00/FF01/FF02)
# Clean output: Pack + Cells + Temps + MOSFET + Cycle + Capacity + Protect + Balance
import bluetooth, time, sys
from micropython import const

# ===== Config =====
TARGET_NAME      = "BMS-BTT_JP"
QUERY_PERIOD_MS  = 1000
POLL_DELAY_MS    = 300
FIRST_KICK_MS    = 250
DEBUG_LEVEL      = 0
DUMP_HEX_BYTES   = False
QUERY_PACK_ONLY  = False   # False -> alternate 0x03 and 0x04
BUF_MAX_BYTES    = 4096

# ===== IRQ codes =====
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
_IRQ_GATTC_READ_RESULT           = const(15)
_IRQ_GATTC_WRITE_STATUS          = const(16)
_IRQ_GATTC_NOTIFY                = const(18)

# ===== UUIDs =====
SVC_UUID    = bluetooth.UUID(0xFF00)
NOTIFY_UUID = bluetooth.UUID(0xFF01)   # read + notify
WRITE_UUID  = bluetooth.UUID(0xFF02)   # write
CCCD_UUID   = bluetooth.UUID(0x2902)

# ===== Commands =====
CMD_BASIC = bytes([0xDD,0xA5,0x03,0x00,0xFF,0xFD,0x77])  # pack/basic info
CMD_CELLS = bytes([0xDD,0xA5,0x04,0x00,0xFF,0xFC,0x77])  # per-cell mV

# ===== Helpers =====
def safe_print(*args):
    try:
        print(" ".join(str(a) for a in args))
    except Exception:
        for a in args:
            try: print(str(a), end=" ")
            except Exception: print("[unprintable]", end=" ")
        print()

def now_ms(): return time.ticks_ms()

# --- framing (no deletions; head pointer) ---
_buf = bytearray()
_head = 0

def _buf_clear():
    global _buf, _head
    _buf = bytearray(); _head = 0

def _maybe_compact(force=False):
    global _buf, _head
    if _head and (force or _head > 1024 or _head > (len(_buf) >> 1)):
        _buf = _buf[_head:]; _head = 0

def push_bytes(chunk):
    global _buf, _head
    if not chunk: return
    unread = len(_buf) - _head
    incoming = len(chunk)
    total_after = unread + incoming
    if total_after > BUF_MAX_BYTES:
        drop = total_after - BUF_MAX_BYTES
        if drop >= unread:
            _buf_clear()
        else:
            _head += drop
            _maybe_compact()
    _buf.extend(chunk)

def pop_frame():
    global _buf, _head
    while True:
        n = len(_buf) - _head
        if n < 5: return None
        mv = memoryview(_buf)[_head:]
        # find 0xDD
        j = 0
        while j < n and mv[j] != 0xDD: j += 1
        if j >= n:
            _buf_clear(); return None
        if j:
            _head += j; _maybe_compact()
            n = len(_buf) - _head
            if n < 5: return None
            mv = memoryview(_buf)[_head:]
        ln = (mv[2] << 8) | mv[3]
        total = 1 + 1 + 2 + ln + 2 + 1
        if total <= 0 or total > BUF_MAX_BYTES:
            _head += 1; _maybe_compact(); continue
        if n < total: return None
        f = bytes(mv[:total])
        _head += total; _maybe_compact()
        if f[-1] == 0x77: return f
        _head += 1; _maybe_compact()

# ===== Decoders =====
def frame_ok(f):
    if (not f) or (len(f) < 7) or (f[0] != 0xDD) or (f[-1] != 0x77): return False
    recv = (f[-3] << 8) | f[-2]
    n = len(f)
    def ok(start, end_excl):
        if end_excl <= start: return False
        s = 0
        for b in f[start:end_excl]:
            s = (s + b) & 0xFFFF
        calc = (0x10000 - s) & 0xFFFF
        return calc == recv
    for st in (0,1,2,3):
        for en in (n-3, n-4):
            if ok(st, en): return True
    return False

def s16(msb, lsb):
    v = ((msb << 8) | lsb) & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v

def u16(msb, lsb):
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
        if bits & (1 << b): out.append(name)
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

def parse_basic(f):
    if (not frame_ok(f)) or (f[1] != 0x03): return None
    d = f[4:-3]
    if len(d) < 23: return None
    voltage_v   = ((d[0] << 8) | d[1]) / 100.0
    current_a   = s16(d[2], d[3]) / 100.0
    cap_rem_ah  = u16(d[4], d[5]) / 100.0
    cap_full_ah = u16(d[6], d[7]) / 100.0
    cycle_cnt   = u16(d[8], d[9])
    prod_date   = u16(d[10], d[11])
    bal_bytes   = d[12:16]
    prot_bits   = u16(d[16], d[17])
    version     = d[18]
    soc_pct     = d[19]
    fet_flags   = d[20]
    cells       = d[21]
    ntc_count   = d[22]
    temps = []
    off = 23
    for _ in range(ntc_count):
        if off + 1 >= len(d): break
        raw = u16(d[off], d[off+1])
        temps.append((raw / 10.0) - 273.1)
        off += 2
    y, m, day   = _decode_prod_date(prod_date)
    prot_list   = _recognized_protections(prot_bits)
    fet_chg     = 1 if (fet_flags & 0x01) else 0
    fet_dsg     = 1 if (fet_flags & 0x02) else 0
    balancing   = _balance_cells_from_bitmap(bal_bytes, cells)
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
        "version": version,
    }

def parse_cells(f):
    if (not frame_ok(f)) or (f[1] != 0x04): return None
    d = f[4:-3]
    out = []
    i = 0
    n = len(d)
    while i + 1 < n:
        mv = (d[i] << 8) | d[i+1]
        if 0 < mv < 6000: out.append(mv / 1000.0)
        i += 2
    return out or None

# --- advertising helpers ---
def adv_iter(adv):
    i = 0; n = len(adv)
    while i + 1 < n:
        L = adv[i]
        if L == 0: return
        t = adv[i+1]; p = adv[i+2:i+1+L]
        yield t, p
        i += 1 + L

def adv_name(adv):
    for t, p in adv_iter(adv):
        if (t == 0x09) or (t == 0x08):
            try: return p.decode("utf-8")
            except: return bytes(p).decode("utf-8", "ignore")
    return None

# ===== Client =====
class Client:
    def __init__(self, ble):
        self.ble = ble
        self.ble.active(True)
        self.ble.irq(self._irq)
        self.conn = None
        self.srange = None
        self.h_n = None
        self.h_w = None
        self.h_cccd = None
        self.next_ms = 0
        self.awaiting = False
        self.phase = 0
        self.last_data_ms = 0
        self.last_cells = None

    def _irq(self, e, d):
        try:
            if e == _IRQ_SCAN_RESULT:
                at, addr, atype, rssi, adv = d
                nm = adv_name(bytes(adv)) or ""
                if nm == TARGET_NAME:
                    safe_print("Found", nm)
                    self.ble.gap_scan(None)
                    self.ble.gap_connect(at, addr)
            elif e == _IRQ_PERIPHERAL_CONNECT:
                self.conn, _, _ = d
                safe_print("Connected. Handle:", self.conn)
                self.ble.gattc_discover_services(self.conn)
            elif e == _IRQ_GATTC_SERVICE_RESULT:
                ch, start, end, uuid = d
                if ch == self.conn and uuid == SVC_UUID:
                    self.srange = (start, end)
            elif e == _IRQ_GATTC_SERVICE_DONE:
                if self.srange:
                    s, e2 = self.srange
                    self.ble.gattc_discover_characteristics(self.conn, s, e2)
                else: self._restart()
            elif e == _IRQ_GATTC_CHARACTERISTIC_RESULT:
                ch, _, val_h, props, uuid = d
                if ch != self.conn: return
                if uuid == NOTIFY_UUID: self.h_n = val_h
                elif uuid == WRITE_UUID: self.h_w = val_h
            elif e == _IRQ_GATTC_CHARACTERISTIC_DONE:
                if self.h_n is not None:
                    self.ble.gattc_discover_descriptors(self.conn, self.h_n, self.h_n+3)
                    self._schedule_send(FIRST_KICK_MS)
                else: self._restart()
            elif e == _IRQ_GATTC_DESCRIPTOR_RESULT:
                ch, dh, duuid = d
                if ch == self.conn and duuid == CCCD_UUID and dh == (self.h_n + 1):
                    self.h_cccd = dh
            elif e == _IRQ_GATTC_DESCRIPTOR_DONE:
                if self.h_cccd:
                    try: self.ble.gattc_write(self.conn, self.h_cccd, b"\x01\x00", 1)
                    except: pass
            elif e == _IRQ_GATTC_NOTIFY:
                ch, vh, nd = d
                if ch == self.conn and vh == self.h_n:
                    push_bytes(bytes(nd))
                    self.awaiting = False
                    self.last_data_ms = now_ms()
            elif e == _IRQ_GATTC_READ_RESULT:
                ch, vh, rd = d
                if ch == self.conn and vh == self.h_n:
                    push_bytes(bytes(rd))
                    self.awaiting = False
                    self.last_data_ms = now_ms()
            elif e == _IRQ_PERIPHERAL_DISCONNECT:
                ch, _, _ = d
                if ch == self.conn:
                    safe_print("Disconnected.")
                    self._restart()
        except: pass

    def _restart(self):
        self.conn = None; self.srange = None
        self.h_n = None; self.h_w = None; self.h_cccd = None
        self.next_ms = 0; self.awaiting = False; self.phase = 0
        self.last_data_ms = 0; self.last_cells = None
        _buf_clear()
        self.scan(8000)

    def _schedule_send(self, delay_ms):
        self.next_ms = time.ticks_add(now_ms(), delay_ms)
        self.awaiting = False

    def _print_cells(self, cells):
        lbls = []
        for idx, cv in enumerate(cells, 1):
            lbls.append("%d:%.3f" % (idx, cv))
        safe_print("Cells:", " ".join(lbls), "V")

    def _drain_frames_mainloop(self):
        any_out = False
        while True:
            f = pop_frame()
            if not f: break
            any_out = True
            cmd = f[1]
            if cmd == 0x03:
                info = parse_basic(f)
                if info:
                    line1 = ["Pack: %.2f V" % info["voltage_v"],
                             "I=%.2f A" % info["current_a"],
                             "SOC=%d%%" % info["soc_pct"],
                             "MOSFETs: CHG=%s DSG=%s" % ("on" if info["fet_chg"] else "off",
                                                         "on" if info["fet_dsg"] else "off")]
                    safe_print(" | ".join(line1))
                    safe_print("Cycles=%d | Cap(full)=%.2f Ah | Cap(remaining)=%.2f Ah" %
                               (info["cycle_cnt"], info["cap_full_ah"], info["cap_rem_ah"]))
                    prot = info["prot_list"]
                    safe_print("Protection: %s" % (", ".join(prot) if prot else "none"))
                    bals = info["balance_cells"]
                    safe_print("Balancing: %s" % (",".join(str(x) for x in bals) if bals else "none"))
                    ts = info["temps_c"]
                    if ts: safe_print("Temps:", " ".join("%.1f°C" % t for t in ts))
                if self.last_cells: self._print_cells(self.last_cells)
            elif cmd == 0x04 and not QUERY_PACK_ONLY:
                cells = parse_cells(f)
                if cells:
                    self.last_cells = cells
                    self._print_cells(cells)
        return any_out

    def tick(self):
        try:
            _ = self._drain_frames_mainloop()
            if (self.conn is None) or (self.h_n is None): return
            t = now_ms()
            if self.next_ms and time.ticks_diff(t, self.next_ms) >= 0:
                self.next_ms = 0
                if (not self.awaiting) and (self.h_w is not None):
                    payload = CMD_BASIC if (QUERY_PACK_ONLY or self.phase == 0) else CMD_CELLS
                    try: self.ble.gattc_write(self.conn, self.h_w, payload, 0)
                    except:
                        try: self.ble.gattc_write(self.conn, self.h_w, payload, 1)
                        except: pass
                    self.awaiting = True
                    self.next_ms  = time.ticks_add(t, POLL_DELAY_MS)
                    if not QUERY_PACK_ONLY: self.phase ^= 1
                elif self.awaiting:
                    try: self.ble.gattc_read(self.conn, self.h_n)
                    except: pass
                    self.awaiting = False
                    self.next_ms  = time.ticks_add(now_ms(), QUERY_PERIOD_MS)
            if self.last_data_ms and time.ticks_diff(t, self.last_data_ms) > (QUERY_PERIOD_MS*3) and (not self.awaiting):
                self._schedule_send(100)
        except Exception as ex:
            safe_print("tick exception:", ex)
            sys.print_exception(ex)

    def scan(self, ms):
        safe_print("Scanning…")
        try:
            self.ble.gap_scan(ms, 30000, 30000)
        except Exception as ex:
            safe_print("gap_scan error:", ex)

# ===== main =====
ble = bluetooth.BLE()
cli = Client(ble)
cli.scan(8000)

while True:
    cli.tick()
    time.sleep_ms(500)
