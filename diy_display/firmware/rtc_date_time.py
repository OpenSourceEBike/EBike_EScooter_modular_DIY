import wifi
import socketpool
import adafruit_ntp
import busio
import adafruit_ds3231

import rtc

class RTCDateTime(object):

    def __init__(self, rtc_scl_pin = None, rtc_sda_pin = None):

        # i2c = busio.I2C(rtc_scl_pin, rtc_sda_pin)
        # self._rtc = adafruit_ds3231.DS3231(i2c)
        
        self._rtc = rtc.RTC()

    def update_date_time_from_wifi_ntp(self):
        # Get date and time from WiFi NTP
        wifi_ssid = "HomeSweetHome"
        wifi_password = "verygood"
        
        state = True
        try:
            wifi.radio.connect(wifi_ssid, wifi_password)    
            if not wifi.radio.ipv4_address:  # Double-check connection
                print("Connected to WiFi, but no IP address assigned.")
                state = False
            print(f"Connected to WiFi: {wifi_ssid}")
        except ConnectionError:
            print("Failed to connect to WiFi with provided credentials")
            state = False

        if state:
            try:
                pool = socketpool.SocketPool(wifi.radio)
                ntp = adafruit_ntp.NTP(pool, tz_offset=0, cache_seconds=3600)
                
                # Set the RTC time
                self._rtc.datetime = ntp.datetime
                print(f"RTC updated to: {self._rtc.datetime}")
                state = True
            except Exception as e:
                print(f"Failed to fetch time from NTP server: {e}")
                state = False
        
        # Wifi radio needs to reset otherwise ESPNOW will not work
        wifi.radio.enabled = False
        wifi.radio.enabled = True
        
        if state:
            return True
        else:
            return False
    
    def date_time(self):
        return self._rtc.datetime
