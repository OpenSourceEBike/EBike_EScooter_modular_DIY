import wifi
import socketpool
import adafruit_ntp
import busio
import adafruit_ds3231
import rtc

class RTCDateTime(object):

    def __init__(self, rtc_scl_pin = None, rtc_sda_pin = None):

        self._rtc_external = None

        # Try initialize RTC external based on DS3231
        i2c = busio.I2C(rtc_scl_pin, rtc_sda_pin)
        try:
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

    def update_date_time_from_wifi_ntp(self):
        wifi_ssid = None
        wifi_password = None
        ntp_datetime_state = 0
        
        # Get wifi ssid and password
        import secrets
        try:
            wifi_ssid = secrets.secrets['wifi_ssid']
            wifi_password = secrets.secrets['wifi_password']
            ntp_datetime_state = 1
        except KeyError:
            print("Secrets are missing from secrets.py!")
        
        # Get date and time from WiFi NTP
        if ntp_datetime_state == 1:
            try:
                wifi.radio.connect(wifi_ssid, wifi_password)  
                if not wifi.radio.ipv4_address:  # Double-check connection
                    print("Connected to WiFi, but no IP address assigned.")
                
                print(f"Connected to WiFi: {wifi_ssid}")
                ntp_datetime_state = 2
                
            except ConnectionError:
                print("Failed to connect to WiFi with provided credentials")
                
            # Wifi radio needs to reset otherwise ESPNOW will not work
            wifi.radio.enabled = False
            wifi.radio.enabled = True

            if ntp_datetime_state == 2:
                try:
                    pool = socketpool.SocketPool(wifi.radio)
                    ntp = adafruit_ntp.NTP(pool, tz_offset=0, cache_seconds=3600)
                    
                    # Set the RTC time
                    self._rtc_internal.datetime = ntp.datetime
                    print(f"RTC internal updated to: {self._rtc_external.datetime}")

                    # Update datetime on external RTC                    
                    if self._rtc_external is not None:
                        self._rtc_external.datetime = self._rtc_internal.datetime
                        print(f"RTC external updated to: {self._rtc_external.datetime}")

                    ntp_datetime_state = 3
                except Exception as e:
                    print(f"Failed to fetch time from NTP server: {e}")
                    if self.update_internal_rtc_from_external():
                        ntp_datetime_state = 4     
        else:
            if self.update_internal_rtc_from_external():
                ntp_datetime_state = 4
                
        # Return True if RTC internal has correct datetime
        if ntp_datetime_state == 3 or ntp_datetime_state == 4:
            return True
        
        elif ntp_datetime_state == 1:
            if self.update_internal_rtc_from_external():
                return True
            else:
                return False
        else:
            return False
         
    def date_time(self):
        return self._rtc_internal.datetime
