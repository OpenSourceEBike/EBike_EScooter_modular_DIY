import time
import network
import uasyncio as asyncio
import aioespnow
import machine

from lcd.lcd_st7565 import LCD
from fonts import ac437_hp_150_re_12
from fonts import freesans20
from fonts import freesansbold50
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from escooter_fiido_q1_s.power_switch_espnow import PowerSwitch
from escooter_fiido_q1_s.front_lights_espnow import FrontLights
from escooter_fiido_q1_s.rear_lights_espnow import RearLights
from firmware_common.thisbutton import thisButton
from firmware_common.utils import map_range

import vars as Vars

# ---------------- Config ----------------
my_mac_address             = b"\x68\xb6\xb3\x01\xf7\xf3"  # display
mac_address_power_switch   = b"\x68\xb6\xb3\x01\xf7\xf1"
mac_address_motor_board    = b"\x68\xb6\xb3\x01\xf7\xf2"
mac_address_rear_lights    = b"\x68\xb6\xb3\x01\xf7\xf4"
mac_address_front_lights   = b"\x68\xb6\xb3\x01\xf7\xf5"

LCD_W, LCD_H = 128, 64
ESP_CHANNEL = 1

BTN_POWER, BTN_LIGHTS = 0, 1
BUTTON_PINS = [5, 6]  # POWER=IO5, LIGHTS=IO6

# ----- Rear/front light bit masks
REAR_TAIL_BIT       = 1
REAR_STOP_BIT       = 2
FRONT_HEAD_BIT      = 1

# -------------- Helpers -----------------
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

# -------------- Main --------------------
async def main():
    print("Starting Display")
    vars = Vars.Vars()

    vars.shutdown_request = False
    vars.rear_lights_board_pins_state = 0
    vars.front_lights_board_pins_state = 0
    vars.lights_state = False

    # WiFi STA
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    try:
        sta.config(mac=my_mac_address)
    except Exception:
        pass
    try:
        try:
            sta.disconnect()
        except Exception:
            pass
        sta.config(channel=ESP_CHANNEL)
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

    motor = MotorBoard(espnow, mac_address_motor_board, radio_lock, vars)
    await motor.start()
    power_switch = PowerSwitch(espnow, mac_address_power_switch, radio_lock, vars)
    front_lights = FrontLights(espnow, mac_address_front_lights, radio_lock, vars)
    rear_lights  = RearLights(espnow, mac_address_rear_lights, radio_lock, vars)

    # LCD
    lcd = LCD(
        spi_clk_pin=3, spi_mosi_pin=4, chip_select_pin=1,
        command_pin=2, reset_pin=0, backlight_pin=21,
        spi_clock_frequency=10_000_000,
    )
    lcd.backlight_pwm(0.5)
    fb = lcd.display
    lcd.clear()
    lcd.display.show()

    rtc = RTCDateTime(rtc_scl_pin=9, rtc_sda_pin=8)

    # UI Widgets
    wheel_speed_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                       font=freesansbold50,
                                       left=0, top=2, right=1, bottom=0,
                                       align_inside="right",
                                       debug_box=False)
    wheel_speed_widget.set_box(x1=LCD_W - 55, y1=0, x2=LCD_W - 1, y2=36)

    warning_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                   font=ac437_hp_150_re_12,
                                   align_inside="left")
    warning_widget.set_box(x1=0, y1=38, x2=63, y2=38+9)

    clock_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                 font=freesans20,
                                 align_inside="right")
    clock_widget.set_box(x1=LCD_W-52, y1=LCD_H-17, x2=LCD_W-3, y2=LCD_H-2)

    main_screen_widget_1 = WidgetTextBox(fb, LCD_W, LCD_H,
                                         font=freesans20,
                                         align_inside="center")
    main_screen_widget_1.set_box(x1=0, y1=int(LCD_H/4)*1, x2=LCD_W-1, y2=int(LCD_H/4)*2)

    main_screen_widget_2 = WidgetTextBox(fb, LCD_W, LCD_H,
                                         font=freesans20,
                                         align_inside="center")
    main_screen_widget_2.set_box(x1=0, y1=int(LCD_H/4)*3, x2=LCD_W-1, y2=int(LCD_H/4)*4)

    nr_buttons = len(BUTTON_PINS)
    button_POWER, button_LIGHTS = range(nr_buttons)

    # --------- Strict power-off path ----------
    async def turn_off_execute():
        await motor.send_data_async()
        await power_switch.send_data_async()
        await front_lights.send_data_async()
        await rear_lights.send_data_async()

    async def turn_off():
        # Request OFF states for all boards once
        vars.turn_off_relay = True
        vars.motor_enable_state = False
        vars.front_lights_board_pins_state = 0
        vars.rear_lights_board_pins_state = 0

        # One-shot static "POWER OFF"
        lcd.clear()
        main_screen_widget_1.update("Ready to")
        main_screen_widget_2.update("POWER OFF")
        lcd.display.show()

        # Block forever here: no UI updates, no timers
        buttons_state_previous = bool(vars.buttons_state & 0x0100)
        while True:
            # Poll just the POWER button; reset on press
            buttons[button_POWER].tick()
            if bool(vars.buttons_state & 0x0100) != buttons_state_previous:
                machine.reset()

            # Keep telling the power switch to remain off
            await turn_off_execute()
            await asyncio.sleep_ms(150)

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

    buttons = [None]*nr_buttons
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
        buttons[i] = btn

    async def wait_for_power_on():
        lcd.clear()
        main_screen_widget_1.update("Ready to")
        main_screen_widget_2.update("POWER ON")
        lcd.display.show()
        vars.buttons_state = 0

        while True:
            buttons[button_POWER].tick()
            if bool(vars.buttons_state & 0x0100):
                break
            await motor.send_data_async()
            await asyncio.sleep_ms(80)

        vars.motor_enable_state = True

    await wait_for_power_on()

    # ------------- Main screen -------------
    lcd.clear()
    motor_power_widget = MotorPowerWidget(fb, LCD_W, LCD_H)
    battery_soc_widget = BatterySOCWidget(fb, LCD_W, LCD_H)
    battery_soc_widget.draw_contour()
    lcd.display.show()

    # --- trackers ---
    battery_soc_prev = 9999
    motor_power_prev = 9999
    wheel_speed_prev = 9999
    brakes_prev = False
    vesc_fault_prev = 9999

    time_buttons        = time.ticks_ms()
    time_display        = time.ticks_ms()
    time_motor_tx       = time.ticks_ms()
    time_motor_rx       = time.ticks_ms()
    time_lights_tx      = time.ticks_ms()
    time_tick           = time.ticks_ms()
    t_rtc_try_update_once = time.ticks_ms()
    update_date_time_once = False

    # Main loop
    while True:
        
        if vars.shutdown_request:
            await turn_off()  # NEVER RETURNS

        now_ms = time.ticks_ms()

        # UI
        if time.ticks_diff(now_ms, time_display) > 150:
            time_display = now_ms

            # Battery
            if battery_soc_prev != vars.battery_soc_x1000:
                battery_soc_prev = vars.battery_soc_x1000
                battery_soc_widget.update(int(vars.battery_soc_x1000/10))

            # Motor power
            vars.motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x10) / 100.0)
            if motor_power_prev != vars.motor_power:
                motor_power_prev = vars.motor_power
                motor_power = filter_motor_power(vars.motor_power)
                motor_power_percent = map_range(motor_power, 0, 2000, 0, 100, clamp=True)
                motor_power_widget.update(motor_power_percent)

            # Wheel speed
            if wheel_speed_prev != vars.wheel_speed_x10:
                wheel_speed_prev = vars.wheel_speed_x10
                wheel_speed_widget.update(int(vars.wheel_speed_x10 / 10))

            lcd.display.show()

        # Motor RX
        if time.ticks_diff(now_ms, time_motor_rx) > 100:
            time_motor_rx = now_ms
            motor.receive_process_data()

            if brakes_prev != vars.brakes_are_active:
                brakes_prev = vars.brakes_are_active
                warning_widget.update("brakes" if vars.brakes_are_active else "")
                lcd.display.show()
            elif vesc_fault_prev != vars.vesc_fault_code:
                vesc_fault_prev = vars.vesc_fault_code
                warning_widget.update("" if not vars.vesc_fault_code else "mot e: %d" % vars.vesc_fault_code)
                lcd.display.show()

        # Motor TX
        if time.ticks_diff(now_ms, time_motor_tx) > 150:
            time_motor_tx = now_ms
            await motor.send_data_async()

        # Buttons
        if time.ticks_diff(now_ms, time_buttons) > 50:
            time_buttons = now_ms
            for i in range(len(buttons)):
                buttons[i].tick()

        # Lights
        if time.ticks_diff(now_ms, time_lights_tx) > 50:
            time_lights_tx = now_ms

            # Brake light (on brake OR strong regen current)
            if vars.brakes_are_active or vars.motor_current_x10 < -150:
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

            front_lights.send_data()
            rear_lights.send_data()

        # Try NTP once after ~2s
        if (not update_date_time_once) and time.ticks_diff(now_ms, t_rtc_try_update_once) > 2000:
            update_date_time_once = True
            try:
                rtc.update_date_time_from_wifi_ntp()
            except Exception as ex:
                print(ex)

        # Time draw (1 Hz)
        if time.ticks_diff(now_ms, time_tick) > 1000:
            time_tick = now_ms
            try:
                dt = rtc.date_time()
                h, m = dt[3], dt[4]
                time_str = ('{:01d}:{:02d}' if h < 10 else '{:02d}:{:02d}').format(h, m)
                clock_widget.update(time_str)
                lcd.display.show()
            except Exception as ex:
                clock_widget.update('')
                lcd.display.show()
                print(ex)

        await asyncio.sleep_ms(10)

# Entry
try:
    asyncio.run(main())
finally:
    pass
