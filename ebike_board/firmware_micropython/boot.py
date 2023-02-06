# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
print("Activating network")
import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.config(dhcp_hostname="display")
wlan.connect('xxxx', 'xxxx')

print("Starting webrepl")
import webrepl
webrepl.start()

print("Starting IDE web service")
import weditor.start
