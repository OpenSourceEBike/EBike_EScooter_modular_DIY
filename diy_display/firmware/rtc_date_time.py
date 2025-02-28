import wifi
import socketpool
import adafruit_ntp
import busio
import adafruit_ds3231
import asyncio

class RTCDateTime(object):

    def __init__(self, rtc_scl_pin = None, rtc_sda_pin = None):

        i2c = busio.I2C(rtc_scl_pin, rtc_sda_pin)
        self._rtc = adafruit_ds3231.DS3231(i2c)
        
        # start the task
        asyncio.create_task(self.update_date_time())

    # this task will only run once
    async def update_date_time(self):
        
        # non-blocking delay some seconds to not block the boot time
        await asyncio.sleep(5)
        
        # get date time from wifi NTP
        # get wifi AP credentials from a settings.toml file
        wifi_ssid = "HomeSweetHome"
        wifi_password = "verygood"

        if wifi_ssid is None:
            raise ValueError("SSID not found in environment variables")

        try:
            wifi.radio.connect(wifi_ssid, wifi_password)
        except ConnectionError:
            print("Failed to connect to WiFi with provided credentials")
            raise

        pool = socketpool.SocketPool(wifi.radio)
        ntp = adafruit_ntp.NTP(pool, tz_offset=0, cache_seconds=3600)
        
        # Set the time date to RTC
        self._rtc.datetime = ntp.datetime
    
    def date_time(self):
        return self._rtc.datetime
