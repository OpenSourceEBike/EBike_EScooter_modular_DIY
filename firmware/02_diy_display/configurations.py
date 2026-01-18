from micropython import const

# model = 'escooter_fiido_q1_s'
model = 'escooter_iscooter_i12'

# ESPNow wireless communications uses this MAC address
if model == 'escooter_fiido_q1_s':
    # Fiido Q1S
    my_mac_address             = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF3]  # display
    mac_address_power_switch   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF1]
    mac_address_motor_board    = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF2]
    mac_address_rear_lights    = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF4]
    mac_address_front_lights   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xF5]
    
elif model == 'escooter_iscooter_i12':
    my_mac_address             = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE3]  # display
    mac_address_power_switch   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE1]
    mac_address_motor_board    = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE2]
    mac_address_rear_lights    = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE4]
    mac_address_front_lights   = [0x68, 0xB6, 0xB3, 0x01, 0xF7, 0xE5]

elif model == 'ebike_bafang_m500':
    pass
elif model == 'escooter_xiaomi_m365':
    pass
else:
    raise 'You need to select a valid EBike/EScooter model'

# LCD ST7565 pins
pin_spi_mosi                = const(43)
pin_spi_clk                 = const(44)
pin_dc                      = const(13)
pin_cs                      = const(12)
pin_rst                     = const(11)
pin_bl                      = const(10)

spi_baud                    = const(10_000_000)

enable_rtc_time             = True
rtc_scl_pin                 = const(8)
rtc_sda_pin                 = const(7)

# Power button pin (active-low with PULL_UP)
power_button_pin = const(6)
lights_button_pin = const(5)

# Long-press
power_btn_long_ms = const(700)
debounce_ms       = const(30)

# UI
ui_hz = const(10)
poweroff_countdown_s = const(3)