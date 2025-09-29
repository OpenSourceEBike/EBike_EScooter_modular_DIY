# rtc_datetime_mpy.py — MicroPython version (ESP32/ESP32-C3)
# Returns tuples, not time.struct_time (MicroPython has no struct_time).

import time
import machine
import network
import ntptime

# ---------- Minimal DS3231 driver (I2C) ----------
class DS3231:
    def __init__(self, i2c, addr=0x68):
        self.i2c = i2c
        self.addr = addr

    @staticmethod
    def _bcd2bin(x):
        return (x >> 4) * 10 + (x & 0x0F)

    @staticmethod
    def _bin2bcd(x):
        return ((x // 10) << 4) | (x % 10)

    def datetime(self):
        """
        Return current time as an 8-tuple:
          (year, month, day, hour, minute, second, weekday, yearday)
        weekday: 0=Mon..6=Sun (MicroPython style)
        yearday is set to 0 (not used)
        """
        data = self.i2c.readfrom_mem(self.addr, 0x00, 7)
        sec   = self._bcd2bin(data[0] & 0x7F)
        minute= self._bcd2bin(data[1] & 0x7F)
        hour  = self._bcd2bin(data[2] & 0x3F)  # 24h assumed
        # DS3231 weekday: 1=Sun..7=Sat -> convert to 0=Mon..6=Sun
        ds_wday = (data[3] & 0x07) or 7  # treat 0 as 7
        wday = (ds_wday % 7)  # Sun(1)->1%7=1, we need 6; adjust below
        # fix: map DS3231 1..7 (Sun..Sat) to 0..6 (Mon..Sun)
        # Build a small map: Sun->6, Mon->0, Tue->1, ... Sat->5
        map_ds_to_mp = {1:6, 2:0, 3:1, 4:2, 5:3, 6:4, 7:5}
        wday = map_ds_to_mp.get(ds_wday, 0)

        day   = self._bcd2bin(data[4] & 0x3F)
        month = self._bcd2bin(data[5] & 0x1F)
        year  = 2000 + self._bcd2bin(data[6])
        return (year, month, day, hour, minute, sec, wday, 0)

    def set_datetime(self, tt):
        """
        Set DS3231 time from a tuple like:
          (Y, M, D, h, m, s, wday, yday)  # MicroPython-style
        or any longer struct with these in the first 7 items.
        Weekday provided as 0=Mon..6=Sun (converted to DS3231 1=Sun..7=Sat).
        """
        year, month, day, hour, minute, sec, wday = tt[:7]
        # convert 0=Mon..6=Sun -> 1=Sun..7=Sat
        map_mp_to_ds = {0:2, 1:3, 2:4, 3:5, 4:6, 5:7, 6:1}
        ds_wday = map_mp_to_ds.get(int(wday) % 7, 1)

        buf = bytearray(7)
        buf[0] = self._bin2bcd(int(sec))
        buf[1] = self._bin2bcd(int(minute))
        buf[2] = self._bin2bcd(int(hour))
        buf[3] = self._bin2bcd(ds_wday)
        buf[4] = self._bin2bcd(int(day))
        buf[5] = self._bin2bcd(int(month))
        buf[6] = self._bin2bcd(int(year) - 2000)
        self.i2c.writeto_mem(self.addr, 0x00, buf)

# ---------- Main class ----------
class RTCDateTime(object):
    def __init__(self, rtc_scl_pin=None, rtc_sda_pin=None, i2c_id=0, i2c_freq=400_000):
        self._rtc_external = None

        # Try initialize external DS3231 on I2C if pins are provided
        try:
            if rtc_scl_pin is not None and rtc_sda_pin is not None:
                scl = machine.Pin(rtc_scl_pin)
                sda = machine.Pin(rtc_sda_pin)
                i2c = machine.I2C(i2c_id, scl=scl, sda=sda, freq=i2c_freq)
                if 0x68 in i2c.scan():
                    self._rtc_external = DS3231(i2c)
                else:
                    print("DS3231 not found on I2C.")
            else:
                print("No I2C pins given; external RTC disabled.")
        except Exception as e:
            print("Error init rtc external:", e)

        # MicroPython internal RTC
        self._rtc_internal = machine.RTC()

    # ---------- DST helpers (Portugal / WET-WEST) ----------
    def _days_in_month(self, year, month):
        # Correct 31-day months
        if month in (1, 3, 5, 7, 8, 10, 12):
            return 31
        if month in (4, 6, 9, 11):
            return 30
        # February
        leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        return 29 if leap else 28

    def _weekday(self, year, month, day):
        # Returns 0=Mon..6=Sun
        return time.localtime(time.mktime((year, month, day, 0, 0, 0, 0, 0)))[6]

    def _last_sunday(self, year, month):
        dim = self._days_in_month(year, month)
        for d in range(dim, dim - 7, -1):
            if self._weekday(year, month, d) == 6:
                return d
        return None

    def _is_dst_portugal(self, year, month, day):
        ms = self._last_sunday(year, 3)    # last Sunday in March
        os_ = self._last_sunday(year, 10)  # last Sunday in October
        current = (month, day)
        dst_start = (3, ms)
        dst_end = (10, os_)
        return (ms is not None and os_ is not None) and (dst_start <= current < dst_end)

    # ---------- Radio helpers ----------
    def _reset_wifi_radio(self):
        try:
            sta = network.WLAN(network.STA_IF)
            sta.active(False)
            time.sleep_ms(200)
            sta.active(True)
        except Exception as e:
            print("Radio reset failed:", e)

    # ---------- Public API ----------
    def update_internal_rtc_from_external(self):
        if self._rtc_external is not None:
            now = self._rtc_external.datetime()  # 8-tuple
            # machine.RTC().datetime expects: (Y,M,D,weekday,h,m,s,us)
            tup = (now[0], now[1], now[2], now[6], now[3], now[4], now[5], 0)
            self._rtc_internal.datetime(tup)
            print("RTC internal updated from external to:", time.localtime())
            return True
        return False

    def _connect_wifi(self, ssid, password, timeout_s=15):
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        if not sta.isconnected():
            sta.connect(ssid, password)
            t0 = time.ticks_ms()
            while not sta.isconnected():
                if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
                    raise OSError("WiFi connect timeout")
                time.sleep_ms(200)
        return sta

    def update_datetime_from_wifi_ntp(self, ssid=None, password=None):
        # Read secrets.py if not provided
        if ssid is None or password is None:
            try:
                import secrets
                ssid = ssid or secrets.secrets["wifi_ssid"]
                password = password or secrets.secrets["wifi_password"]
            except Exception:
                print("Missing or invalid secrets.py!")
                return self.update_internal_rtc_from_external()

        try:
            sta = self._connect_wifi(ssid, password)
            print("Connected to WiFi:", ssid)

            try:
                ntptime.host = "pool.ntp.org"
                ntptime.settime()  # sets internal RTC to UTC
                now = time.localtime()  # UTC tuple (Y,M,D,h,m,s,wday,yday)

                # Adjust to Portugal local time (DST +1h when active)
                if self._is_dst_portugal(now[0], now[1], now[2]):
                    ts = time.mktime(now) + 3600
                    now = time.localtime(ts)
                    print("Portugal DST active (UTC+1): %02d:%02d:%02d" % (now[3], now[4], now[5]))
                else:
                    print("Portugal DST not active (UTC): %02d:%02d:%02d" % (now[3], now[4], now[5]))

                # Set internal RTC (weekday=now[6], us=0)
                self._rtc_internal.datetime((now[0], now[1], now[2], now[6], now[3], now[4], now[5], 0))
                print("RTC internal updated to:", time.localtime())

                # Also set external RTC if present (store local-adjusted time)
                if self._rtc_external is not None:
                    self._rtc_external.set_datetime(now)
                    print("RTC external updated to:", self._rtc_external.datetime())

                self._reset_wifi_radio()
                return True

            except Exception as e:
                print("Error fetching time from NTP:", e)
                self._reset_wifi_radio()
                return self.update_internal_rtc_from_external()

        except Exception as e:
            print("Failed to connect to WiFi:", e)
            self._reset_wifi_radio()
            return self.update_internal_rtc_from_external()

    # --- Aliases for compatibility with your existing code ---
    def update_date_time_from_wifi_ntp(self, *a, **kw):
        return self.update_datetime_from_wifi_ntp(*a, **kw)

    def datetime(self):
        """Return current *local* time as an 8-tuple (MicroPython style)."""
        return time.localtime()

    def date_time(self):
        """Alias kept for compatibility with your CP code."""
        return self.datetime()
