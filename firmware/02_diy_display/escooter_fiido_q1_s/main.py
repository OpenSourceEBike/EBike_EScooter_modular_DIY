import time
import network
import uasyncio as asyncio
import aioespnow
import machine

from lcd.lcd_st7565 import LCD
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from escooter_fiido_q1_s.power_switch_espnow import PowerSwitch
from escooter_fiido_q1_s.front_lights_espnow import FrontLights
from escooter_fiido_q1_s.rear_lights_espnow import RearLights
from common.thisbutton import thisButton
from common.utils import map_range
from screen_manager import ScreenManager
import vars as Vars
import configurations as cfg

# ----- Rear/front light bit masks
REAR_TAIL_BIT       = 1
REAR_STOP_BIT       = 2
FRONT_HEAD_BIT      = 1

print("Starting Display")

# WiFi STA
sta = network.WLAN(network.STA_IF)
sta.active(True)
try:
    sta.config(mac=cfg.my_mac_address)
except Exception:
    pass
try:
    try:
        sta.disconnect()
    except Exception:
        pass
    sta.config(channel=1)
except Exception:
    pass
try:
    ap = network.WLAN(network.AP_IF)
    if ap.active():
        ap.active(False)
except Exception:
    pass

# ESP-NOW
espnow = aioespnow.AIOESPNow()
espnow.active(True)

vars = Vars.Vars()

radio_lock = asyncio.Lock()

motor = MotorBoard(espnow, cfg.mac_address_motor_board, radio_lock, vars)
power_switch = PowerSwitch(espnow, cfg.mac_address_power_switch, radio_lock, vars)
front_lights = FrontLights(espnow, cfg.mac_address_front_lights, radio_lock, vars)
rear_lights  = RearLights(espnow, cfg.mac_address_rear_lights, radio_lock, vars)

lcd = LCD(
    spi_clk_pin=cfg.pin_spi_clk,
    spi_mosi_pin=cfg.pin_spi_mosi,
    chip_select_pin=cfg.pin_cs,
    command_pin=cfg.pin_dc,
    reset_pin=cfg.pin_rst,
    backlight_pin=cfg.pin_bl,
    spi_clock_frequency=cfg.spi_baud,
)
fb = lcd.display
lcd.backlight_pwm(0.1)
lcd.clear()
lcd.display.show()

vars.rtc = RTCDateTime(rtc_scl_pin=9, rtc_sda_pin=8)

BUTTON_PINS = [
    cfg.power_button_pin,
    cfg.lights_button_pin
    ]

nr_buttons = len(BUTTON_PINS)
button_POWER, button_LIGHTS = range(nr_buttons)

def enter_espnow_low_power(sta, ap, espnow_channel=1, txpower_dbm=2):
    """
    Keep ESP-NOW alive but minimize power:
    - disconnect from WiFi AP (no IP traffic)
    - fix channel back to the ESP-NOW channel
    - enable WiFi power-save (modem sleep)
    - reduce TX power (dBm)
    """
    try:
        if sta.isconnected():
            sta.disconnect()
    except Exception as _:
        pass

    # Make sure SoftAP is off
    try:
        if ap.active():
            ap.active(False)
    except Exception as _:
        pass

    # Re-pin the channel used by all your peers (must match!)
    try:
        sta.config(channel=espnow_channel)
    except Exception as _:
        pass

    # Enable power save (MicroPython exposes different names across versions)
    # We try a few common spellings safely.
    try:
        # ESP-IDF style in some firmwares
        WIFI_PM_MAX_MODEM = getattr(network, "WIFI_PM_MAX_MODEM", None)
        WIFI_PM_MIN_MODEM = getattr(network, "WIFI_PM_MIN_MODEM", None)
        WIFI_PS_MAX_MODEM = getattr(network, "WIFI_PS_MAX_MODEM", None)
        WIFI_PS_MIN_MODEM = getattr(network, "WIFI_PS_MIN_MODEM", None)

        if WIFI_PM_MAX_MODEM is not None:
            sta.config(pm=WIFI_PM_MAX_MODEM)      # deepest modem sleep
        elif WIFI_PM_MIN_MODEM is not None:
            sta.config(pm=WIFI_PM_MIN_MODEM)
        elif WIFI_PS_MAX_MODEM is not None:
            sta.config(pm=WIFI_PS_MAX_MODEM)
        elif WIFI_PS_MIN_MODEM is not None:
            sta.config(pm=WIFI_PS_MIN_MODEM)
        else:
            # Some ports use a boolean flag
            sta.config(ps_mode=True)
    except Exception as _:
        pass

    # Lower TX power to the minimum that still works for your distances (dBm)
    try:
        # Typical valid range ~2..20 dBm; tune for reliability
        sta.config(txpower=txpower_dbm)
    except Exception as _:
        pass


def filter_motor_power(p):
    if p < 0:
        if p > -10: p = 0
        elif p > -25: pass
        elif p > -50: p = round(p/2)*2
        elif p > -100: p = round(p/5)*5
        else: p = round(p/10)*10
    else:
        if p < 10: p = 0
        elif p < 25: pass
        elif p < 50: p = round(p/2)*2
        elif p < 100: p = round(p/5)*5
        else: p = round(p/10)*10
    return p    

# --- button callbacks ---
def button_power_click_start_cb():
    vars.buttons_state |= 1
    if vars.buttons_state & 0x0100: vars.buttons_state &= ~0x0100
    else: vars.buttons_state |= 0x0100

def button_power_click_release_cb():
    vars.buttons_state &= ~1

def button_power_long_click_start_cb():
    vars.buttons_state |= 2
    if vars.buttons_state & 0x0200: vars.buttons_state &= ~0x0200
    else: vars.buttons_state |= 0x0200

def button_power_long_click_release_cb():
    vars.buttons_state &= ~2

def button_lights_click_start_cb():
    vars.lights_state = True

def button_lights_click_release_cb():
    vars.lights_state = False

buttons_callbacks = {
    button_POWER: {
        'click_start': button_power_click_start_cb,
        'click_release': button_power_click_release_cb,
        'long_click_start': button_power_long_click_start_cb,
        'long_click_release': button_power_long_click_release_cb
    },
    button_LIGHTS: {
        'click_start': button_lights_click_start_cb,
        'click_release': button_lights_click_release_cb
    },
}

vars.buttons = [None]*nr_buttons
for i, pin in enumerate(BUTTON_PINS):
    btn = thisButton(pin, True)
    btn.setDebounceThreshold(50)
    btn.setLongPressThreshold(1500)
    if 'click_start' in buttons_callbacks[i]:
        btn.assignClickStart(buttons_callbacks[i]['click_start'])
    if 'click_release' in buttons_callbacks[i]:
        btn.assignClickRelease(buttons_callbacks[i]['click_release'])
    if 'long_click_start' in buttons_callbacks[i]:
        btn.assignLongClickStart(buttons_callbacks[i]['long_click_start'])
    if 'long_click_release' in buttons_callbacks[i]:
        btn.assignLongClickRelease(buttons_callbacks[i]['long_click_release'])
    vars.buttons[i] = btn

async def power_off_forever():
    """
    Block forever: keep OFF states latched and only poll POWER to allow a hard reset.
    Any change on POWER bit (0x0100) triggers machine.reset().
    """
    buttons_state_previous = bool(vars.buttons_state & 0x0100)
    while True:
        # Poll just the POWER button
        vars.buttons[button_POWER].tick()
        current = bool(vars.buttons_state & 0x0100)
        if current != buttons_state_previous:
            machine.reset()

        try:
            # Ensure desired OFF states are in vars before calling this
            await motor.send_data_async()
            await power_switch.send_data_async()
            front_lights.send_data()
            rear_lights.send_data()
        except Exception as ex:
            print("send_all_off_once err:", ex)

        await asyncio.sleep_ms(100)

async def ui_task(fb, lcd, vars):

    screen_manager = ScreenManager(fb, vars)
    
    hz = int(cfg.ui_hz) if isinstance(cfg.ui_hz, (int, float)) else 10
    tick = 1 / max(1, hz)
    
    while True:
        screen_manager.update(vars)
        screen_manager.render(vars)
        lcd.show()
    
        await asyncio.sleep(tick)

async def main_task(vars):
    motor_power_previous = 0
    time_counter_previous = 0
    minute_previous = None
    update_date_time_once = False
    time_rtc_try_update_once = time.ticks_ms()

    while True:
        # Motor power
        motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x10) / 100.0)
        if motor_power_previous != motor_power:
            motor_power_previous = motor_power
            motor_power = filter_motor_power(motor_power)
            vars.motor_power = map_range(motor_power, 0, 1800, 0, 100, clamp=True)

        # Buttons
        for i in range(len(vars.buttons)):
            vars.buttons[i].tick()

        # Time
        # Try NTP once after ~2s
        now = time.ticks_ms()
        if (not update_date_time_once) and \
           not vars.screen_boot_waiting and \
           time.ticks_diff(now, time_rtc_try_update_once) > 2000:
            update_date_time_once = True
            try:
                vars.rtc.update_date_time_from_wifi_ntp()
            except Exception as ex:
                print(ex)
            else:
                # We got time; drop to low-power ESP-NOW mode
                enter_espnow_low_power(sta, ap, espnow_channel=1, txpower_dbm=2)
            
        # Shutdown
        if vars.shutdown_request:
            vars.turn_off_relay = True
            vars.motor_enable_state = False
            vars.front_lights_board_pins_state = 0
            vars.rear_lights_board_pins_state = 0
            await power_off_forever()  # never returns

        await asyncio.sleep(0.05)

async def motor_rx_task(vars):
    while True:
        motor.receive_process_data()
        await asyncio.sleep(0.100)

async def motor_tx_task(vars):
    while True:
        await motor.send_data_async()
        await asyncio.sleep(0.150)

async def lights_task(vars):
    while True:
        
        if not vars.screen_boot_waiting:
            # Brake light (on brake OR strong regen current)
            if vars.brakes_are_active or vars.regen_braking_is_active:
                vars.rear_lights_board_pins_state |= REAR_STOP_BIT
            else:
                vars.rear_lights_board_pins_state &= ~REAR_STOP_BIT

            # Head/Tail with main lights_state
            if vars.lights_state:
                vars.front_lights_board_pins_state |= FRONT_HEAD_BIT
                vars.rear_lights_board_pins_state  |= REAR_TAIL_BIT
            else:
                vars.front_lights_board_pins_state &= ~FRONT_HEAD_BIT
                vars.rear_lights_board_pins_state  &= ~REAR_TAIL_BIT
        else:
            vars.front_lights_board_pins_state = 0
            vars.rear_lights_board_pins_state = 0

        front_lights.send_data()
        rear_lights.send_data()

        await asyncio.sleep(0.05)

# Entry
async def main():
    
    await motor.start()
    
    try:
        tasks = [
            asyncio.create_task(ui_task(fb, lcd, vars)),
            asyncio.create_task(motor_rx_task(vars)),
            asyncio.create_task(motor_tx_task(vars)),
            asyncio.create_task(lights_task(vars)),
            asyncio.create_task(main_task(vars))
        ]
        
        await asyncio.gather(*tasks)
        
    finally:
        pass

asyncio.run(main())
