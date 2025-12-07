import time
import network
import uasyncio as asyncio
import espnow
import machine

from lcd.lcd_st7565 import LCD
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from escooter_fiido_q1_s.power_switch_espnow import PowerSwitch
from escooter_fiido_q1_s.front_lights_espnow import FrontLights
from escooter_fiido_q1_s.rear_lights_espnow import RearLights
from common.thisbutton import thisButton
from common.utils import map_range
from screen_manager import ScreenManager, ScreenID
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

# ESP-NOW (síncrono)
esp = espnow.ESPNow()
esp.active(True)

vars = Vars.Vars()

# radio_lock = asyncio.Lock()  # já não é necessário nas novas classes

# Novas assinaturas: (espnow_inst, peer_mac, vars/system_data)
motor = MotorBoard(esp, cfg.mac_address_motor_board, vars)
power_switch = PowerSwitch(esp, cfg.mac_address_power_switch, vars)
front_lights = FrontLights(esp, cfg.mac_address_front_lights, vars)
rear_lights  = RearLights(esp, cfg.mac_address_rear_lights, vars)

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
lcd.backlight_pwm(0.5)
lcd.clear()
lcd.display.show()

screen_manager = ScreenManager(fb, vars)

if cfg.enable_rtc_time:
    vars.rtc = RTCDateTime(rtc_scl_pin=cfg.rtc_scl_pin, rtc_sda_pin=cfg.rtc_sda_pin)

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
            motor.send_data()
            power_switch.send_data()
            front_lights.send_data()
            rear_lights.send_data()
        except Exception as ex:
            print("send_all_off_once err:", ex)

        await asyncio.sleep_ms(100)

async def ui_task(fb, lcd, vars):
    global screen_manager
    
    hz = int(cfg.ui_hz) if isinstance(cfg.ui_hz, (int, float)) else 10
    tick = 1 / max(1, hz)
    
    while True:
        screen_manager.update(vars)
        screen_manager.render(vars)
        lcd.show()
    
        await asyncio.sleep(tick)

async def main_task(vars):
    global screen_manager
    
    motor_power_previous = 0
    time_counter_previous = 0
    update_date_time_once = False
    time_rtc_try_update_once = time.ticks_ms()
    first_transition_to_main_screen = False

    while True:
        now = time.ticks_ms()
        
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
        if not first_transition_to_main_screen and \
            screen_manager.current_is(ScreenID.MAIN):
            first_transition_to_main_screen = True
            time_rtc_try_update_once = now
        
        # Try NTP once after ~2s
        if not update_date_time_once and \
            cfg.enable_rtc_time and \
            screen_manager.current_is(ScreenID.MAIN) and \
            time.ticks_diff(now, time_rtc_try_update_once) > 2000:
            update_date_time_once = True
            try:
                vars.rtc.update_date_time_from_wifi_ntp()
            except Exception as ex:
                print(ex)
            else:
                # We got time; drop to low-power ESP-NOW mode
                enter_espnow_low_power(sta, ap, espnow_channel=1, txpower_dbm=2)
                
        # Time draw (1 Hz)
        if cfg.enable_rtc_time and \
            time.ticks_diff(now, time_counter_previous) > 1000:
            time_counter_previous = now
            try:
                dt = vars.rtc.date_time()
                hour, minute = dt[3], dt[4]
                vars.time_string = ('{:01d}:{:02d}' if hour < 10 else '{:02d}:{:02d}').format(hour, minute)
            except Exception as ex:
                vars.time_string = ''
                print(ex)

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
        motor.send_data()
        await asyncio.sleep(0.150)

async def lights_task(vars):
    global screen_manager
    
    while True:
        if screen_manager.current_is(ScreenID.MAIN):
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
    # Versão não-async do MotorBoard já não precisa de start()
    # await motor.start()
    
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
