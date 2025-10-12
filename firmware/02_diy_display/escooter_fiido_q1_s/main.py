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


BTN_POWER, BTN_LIGHTS = 0, 1

# ----- Rear/front light bit masks
REAR_TAIL_BIT       = 1
REAR_STOP_BIT       = 2
FRONT_HEAD_BIT      = 1

# -------------- Helpers -----------------
# def filter_motor_power(p):
#     if p < 0:
#         if p > -10: p = 0
#         elif p > -25: pass
#         elif p > -50: p = round(p/2)*2
#         elif p > -100: p = round(p/5)*5
#         else: p = round(p/10)*10lcd
#     else:
#         if p < 10: p = 0
#         elif p < 25: pass
#         elif p < 50: p = round(p/2)*2
#         elif p < 100: p = round(p/5)*5
#         else: p = round(p/10)*10
#     return p

    

print("Starting Display")
vars = Vars.Vars()

vars.rear_lights_board_pins_state = 0
vars.front_lights_board_pins_state = 0
vars.lights_state = False

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
lcd.backlight_pwm(0.1)
fb = lcd.display

lcd.clear()
lcd.display.show()

rtc = RTCDateTime(rtc_scl_pin=9, rtc_sda_pin=8)

BTN_POWER, BTN_LIGHTS = 0, 1
BUTTON_PINS = [cfg.power_btn_pin, 6]  # POWER=IO5, LIGHTS=IO6

nr_buttons = len(BUTTON_PINS)
button_POWER, button_LIGHTS = range(nr_buttons)

# --------- Strict power-off path ----------
# async def turn_off_execute():
#     await motor.send_data_async()
#     await power_switch.send_data_async()
#     await front_lights.send_data_async()
#     await rear_lights.send_data_async()

# async def turn_off():
#     # Request OFF states for all boards once
#     vars.turn_off_relay = True
#     vars.motor_enable_state = False
#     vars.front_lights_board_pins_state = 0
#     vars.rear_lights_board_pins_state = 0

#     # Block forever here: no UI updates, no timers
#     buttons_state_previous = bool(vars.buttons_state & 0x0100)
#     while True:
#         # Poll just the POWER button; reset on press
#         vars.buttons[button_POWER].tick()
#         if bool(vars.buttons_state & 0x0100) != buttons_state_previous:
#             machine.reset()

#         # Keep telling the power switch to remain off
#         await turn_off_execute()
#         await asyncio.sleep_ms(150)

# --- button callbacks ---
def button_power_click_start_cb():
    vars.buttons_state |= 1
    if vars.buttons_state & 0x0100: vars.buttons_state &= ~0x0100
    else: vars.buttons_state |= 0x0100

def button_power_click_release_cb():
    vars.buttons_state &= ~1

def button_power_long_click_start_cb():
    # If safe, request shutdown (do NOT create a task; main loop will block into turn_off)
    if vars.motor_enable_state and vars.wheel_speed_x10 < 20:
        vars.shutdown_request = True
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

# async def wait_for_power_on():
#     lcd.clear()
#     main_screen_widget_1.update("Ready to")
#     main_screen_widget_2.update("POWER ON")
#     lcd.display.show()
#     vars.buttons_state = 0

#     while True:
#         vars.buttons[button_POWER].tick()
#         if bool(vars.buttons_state & 0x0100):
#             break
#         await motor.send_data_async()
#         await asyncio.sleep_ms(80)

#     vars.motor_enable_state = True

# await wait_for_power_on()

# ------------- Main screen -------------
# lcd.clear()

# # --- trackers ---
# battery_soc_prev = 9999
# motor_power_prev = 9999
# wheel_speed_prev = 9999
# brakes_prev = False
# vesc_fault_prev = 9999

# time_buttons        = time.ticks_ms()
# time_display        = time.ticks_ms()
# time_motor_tx       = time.ticks_ms()
# time_motor_rx       = time.ticks_ms()
# time_lights_tx      = time.ticks_ms()
# time_tick           = time.ticks_ms()
# t_rtc_try_update_once = time.ticks_ms()
# update_date_time_once = False

async def ui_task(fb, panel, vars):
    global cfg
    
    sm = ScreenManager(fb, vars)
    tick = 1 / cfg.ui_hz
    while True:
        
        sm.update(vars)
        sm.render(vars)
        panel.show()
        
        await asyncio.sleep(tick)    
    
async def main_task(vars):
    
    while True:
        
        for i in range(len(vars.buttons)):
            vars.buttons[i].tick()
        
        await asyncio.sleep(0.05)

# Main loop
# while True:
    

    # # Motor RX
    # if time.ticks_diff(now_ms, time_motor_rx) > 100:
    #     time_motor_rx = now_ms
    #     motor.receive_process_data()



    # # Motor TX
    # if time.ticks_diff(now_ms, time_motor_tx) > 150:
    #     time_motor_tx = now_ms
    #     await motor.send_data_async()

    # # Lights
    # if time.ticks_diff(now_ms, time_lights_tx) > 50:
    #     time_lights_tx = now_ms

    #     # Brake light (on brake OR strong regen current)
    #     if vars.brakes_are_active or vars.motor_current_x10 < -150:
    #         vars.rear_lights_board_pins_state |= REAR_STOP_BIT
    #     else:
    #         vars.rear_lights_board_pins_state &= ~REAR_STOP_BIT

    #     # Head/Tail with main lights_state
    #     if vars.lights_state:
    #         vars.front_lights_board_pins_state |= FRONT_HEAD_BIT
    #         vars.rear_lights_board_pins_state  |= REAR_TAIL_BIT
    #     else:
    #         vars.front_lights_board_pins_state &= ~FRONT_HEAD_BIT
    #         vars.rear_lights_board_pins_state  &= ~REAR_TAIL_BIT

    #     front_lights.send_data()
    #     rear_lights.send_data()

    # # Try NTP once after ~2s
    # if (not update_date_time_once) and time.ticks_diff(now_ms, t_rtc_try_update_once) > 2000:
    #     update_date_time_once = True
    #     try:
    #         rtc.update_date_time_from_wifi_ntp()
    #     except Exception as ex:
    #         print(ex)

    # await asyncio.sleep_ms(10)

# Entry
async def main():
    
    await motor.start()
    
    try:
        tasks = [
            asyncio.create_task(ui_task(fb, lcd, vars)),
            # asyncio.create_task(task_control_motor_limit_current()),
            # asyncio.create_task(task_control_motor(wdt)),
            # asyncio.create_task(task_display_send_data()),
            # asyncio.create_task(task_display_receive_process_data()),
            asyncio.create_task(main_task(vars))
        ]
        
        await asyncio.gather(*tasks)
        
    finally:
        pass

asyncio.run(main())