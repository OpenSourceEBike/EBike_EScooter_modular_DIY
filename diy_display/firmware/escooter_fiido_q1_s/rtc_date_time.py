import wifi
import adafruit_connection_manager
import adafruit_ntp
import busio
import adafruit_ds3231
import rtc
import time

class RTCDateTime(object):

    def __init__(self, rtc_scl_pin = None, rtc_sda_pin = None):

        self._rtc_external = None

        # Try initialize RTC external based on DS3231
        try:
            i2c = busio.I2C(rtc_scl_pin, rtc_sda_pin)
            self._rtc_external = adafruit_ds3231.DS3231(i2c)
        except Exception as e:
            print(f'Error init rtc external: {e}')
            
        # Initialize ESP32 internal RTC
        self._rtc_internal = rtc.RTC()
        
    def update_internal_rtc_from_external(self):
        # Update datetime on external RTC                    
        if self._rtc_external is not None:
            self._rtc_internal.datetime = self._rtc_external.datetime
            print(f"RTC internal updated from external to: {self._rtc_internal.datetime}")
            return True
        else:
            return False
        
    def _last_sunday(self, year, month):
        # Check the last 7 days of the month to find the last Sunday
        for day in range(31, 24, -1):
            try:
                t = time.struct_time((year, month, day, 0, 0, 0, 0, 0, -1))
                wday = time.localtime(time.mktime(t)).tm_wday
                if wday == 6:  # Sunday
                    return day
            except:
                continue
        return None

    def _is_dst_portugal(self, year, month, day):
        """Returns True if DST is active in Portugal on the given date."""
        march_last_sunday = self._last_sunday(year, 3)
        october_last_sunday = self._last_sunday(year, 10)

        current_tuple = (month, day)
        dst_start = (3, march_last_sunday)
        dst_end = (10, october_last_sunday)

        return dst_start <= current_tuple < dst_end
        
    def _reset_wifi_radio(self):
        wifi.radio.enabled = False
        wifi.radio.enabled = True

    def update_date_time_from_wifi_ntp(self):
        wifi_ssid = None
        wifi_password = None
        
        # Get wifi ssid and password
        import secrets
        try:
            wifi_ssid = secrets.secrets['wifi_ssid']
            wifi_password = secrets.secrets['wifi_password']
        except (ImportError, KeyError):
            print("Missing or invalid secrets.py!")
            return False
        
        # Connect to wifi
        try:
            wifi.radio.connect(wifi_ssid, wifi_password)            
            print(f"Connected to WiFi: {wifi_ssid}")
            
            # Get date and time from WiFi NTP
            try:
                pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
                ntp = adafruit_ntp.NTP(pool, tz_offset=0, cache_seconds=3600)
                
                now = ntp.datetime  # Get the current UTC time
                if self._is_dst_portugal(now.tm_year, now.tm_mon, now.tm_mday):
                    # Apply +1 hour for DST
                    adjusted_hour = (now.tm_hour + 1) % 24
                    now = time.struct_time((now.tm_year, now.tm_mon, now.tm_mday,
                                                        adjusted_hour, now.tm_min, now.tm_sec,
                                                        now.tm_wday, now.tm_yday, now.tm_isdst))
                    print(f"Portugal DST is active (UTC+1), time: {now.tm_hour:02}:{now.tm_min:02}:{now.tm_sec:02}")
                else:
                    print(f"Portugal DST is not active (UTC), time: {now.tm_hour:02}:{now.tm_min:02}:{now.tm_sec:02}")
           
                # Set the internal RTC time
                self._rtc_internal.datetime = now
                print(f"RTC internal updated to: {self._rtc_internal.datetime}")

                # Set the external RTC time
                if self._rtc_external is not None:
                    self._rtc_external.datetime = now
                    print(f"RTC external updated to: {self._rtc_external.datetime}")
                    
                # Wifi radio needs to reset otherwise ESPNOW will not work
                self._reset_wifi_radio()
                return True

            except Exception as e:
                print(f"Error fetching time from NTP: {e}")
                
                self._reset_wifi_radio()
                
                # No date time from NTP, try update internal RTC from external RTC
                return self.update_internal_rtc_from_external()
            
        # No wifi connection, try update internal RTC from external RTC
        except ConnectionError:
            print("Failed to connect to WiFi. Check SSID and password.")
            
            self._reset_wifi_radio()
            
            # Try update internal RTC from external RTC
            return self.update_internal_rtc_from_external()
         
    def date_time(self):
        return self._rtc_internal.datetime
