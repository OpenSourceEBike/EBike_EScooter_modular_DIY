# main.py — MicroPython DISPLAY main (ESP32/ESP32-C3) with aioespnow + FreeSans fonts

import time
import network
import uasyncio as asyncio
import aioespnow

from lcd.lcd_st7565 import LCD
from fonts import ac437_hp_150_re_12
from fonts import freesans20
from fonts import freesansbold50
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from firmware_common.thisbutton import thisButton
from firmware_common.utils import map_range

import vars as Vars

# ---------------- Config ----------------
my_mac_address = b"\x68\xb6\xb3\x01\xf7\xf3"
mac_address_motor_board = b"\x68\xb6\xb3\x01\xf7\xf2"

LCD_W, LCD_H = 128, 64
ESP_CHANNEL = 1

# Buttons (adapt pins to your board)
BTN_POWER, BTN_LEFT, BTN_RIGHT = 0, 1, 2
BUTTON_PINS = [5, 6, 7]  # POWER, LEFT, RIGHT

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

    # WiFi STA (channel for ESP-NOW)
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
    esp = aioespnow.AIOESPNow()
    esp.active(True)
    motor = MotorBoard(esp, mac_address_motor_board, vars)
    await motor.start()

    # LCD
    lcd = LCD(
        spi_clk_pin=3, spi_mosi_pin=4, chip_select_pin=1,
        command_pin=2, reset_pin=0, backlight_pin=21,
        spi_clock_frequency=10_000_000,
    )
    lcd.backlight_pwm(0.5)
    fb = lcd.display
    fb.fill(0)
    lcd.display.show()

    # -------- RTC + Time UI --------
    rtc = RTCDateTime(rtc_scl_pin=9, rtc_sda_pin=8)

    # Widgets used on splash + small HUD
    wheel_speed_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                       font=freesansbold50,
                                       left=0, top=2, right=1, bottom=0,
                                       align_inside="right",
                                       debug_box=False)
    wheel_speed_widget.set_box(x1=LCD_W - 55, y1=0, x2=LCD_W - 1, y2=36)
    
    warning_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                   font=ac437_hp_150_re_12,
                                   left=0, top=0, right=0, bottom=0,
                                   align_inside="left",
                                   debug_box=False)
    warning_widget.set_box(x1=0, y1=38, x2=63, y2=38+9)
    
    clock_widget = WidgetTextBox(fb, LCD_W, LCD_H,
                                 font=freesans20,
                                 left=0, top=0, right=0, bottom=0,
                                 align_inside="right",
                                 debug_box=False)
    clock_widget.set_box(x1=LCD_W-52, y1=LCD_H-17, x2=LCD_W-3, y2=LCD_H-2)

    # Splash / power gate widgets
    main_screen_widget_1 = WidgetTextBox(fb, LCD_W, LCD_H,
                                         font=freesans20,
                                         left=0, top=0, right=0, bottom=0,
                                         align_inside="center",
                                         debug_box=False)
    main_screen_widget_1.set_box(x1=0, y1=int(LCD_H/4)*1, x2=LCD_W-1, y2=int(LCD_H/4)*2)
    
    main_screen_widget_2 = WidgetTextBox(fb, LCD_W, LCD_H,
                                         font=freesans20,
                                         left=0, top=0, right=0, bottom=0,
                                         align_inside="center",
                                         debug_box=False)
    main_screen_widget_2.set_box(x1=0, y1=int(LCD_H/4)*3, x2=LCD_W-1, y2=int(LCD_H/4)*4)

    # Buttons
    nr_buttons = len(BUTTON_PINS)
    button_POWER, button_LEFT, button_RIGHT = range(nr_buttons)

    async def turn_off_execute():
        await motor.send_data_async()
        vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024

    async def turn_off():
        vars.motor_enable_state = False
        main_screen_widget_1.update("Ready to")
        main_screen_widget_2.update("POWER OFF")
        lcd.display.show()
        while buttons[button_POWER].isHeld:
            buttons[button_POWER].tick()
            await turn_off_execute()
            await asyncio.sleep_ms(150)
        while not buttons[button_POWER].buttonActive:
            buttons[button_POWER].tick()
            await turn_off_execute()
            await asyncio.sleep_ms(150)
        import sys
        sys.exit()

    def button_power_click_start_cb():
        vars.buttons_state |= 1
        if vars.buttons_state & 0x0100: vars.buttons_state &= ~0x0100
        else: vars.buttons_state |= 0x0100

    def button_power_click_release_cb():
        vars.buttons_state &= ~1

    def button_power_long_click_start_cb():
        if vars.motor_enable_state and vars.wheel_speed_x10 < 20:
            asyncio.create_task(turn_off())
        else:
            vars.buttons_state |= 2
        if vars.buttons_state & 0x0200: vars.buttons_state &= ~0x0200
        else: vars.buttons_state |= 0x0200

    def button_power_long_click_release_cb():
        vars.buttons_state &= ~2

    def noop(): pass

    buttons_callbacks = {
        button_POWER: {
            'click_start': button_power_click_start_cb,
            'click_release': button_power_click_release_cb,
            'long_click_start': button_power_long_click_start_cb,
            'long_click_release': button_power_long_click_release_cb
        },
        button_LEFT:  {'click_start': noop, 'click_release': noop},
        button_RIGHT: {'click_start': noop, 'click_release': noop},
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

    # -------- POWER-ON GATE (splash that waits for button) --------
    async def wait_for_power_on():
        fb.fill(0)
        main_screen_widget_1.update("Ready to")
        main_screen_widget_2.update("POWER ON")
        lcd.display.show()

        pressed = False
        while True:
            buttons[button_POWER].tick()

            # detect full click (press then release)
            if not pressed and buttons[button_POWER].isHeld:
                pressed = True
            if pressed and not buttons[button_POWER].isHeld:
                break

            # lightweight heartbeat so peer sees us alive
            await motor.send_data_async()

            await asyncio.sleep_ms(80)

        vars.motor_enable_state = True
        main_screen_widget_1.update("Starting…")
        main_screen_widget_2.update("")
        lcd.display.show()
        await asyncio.sleep_ms(200)

    # Run the gate before drawing the main UI
    await wait_for_power_on()

    # ------------- Main screen (widgets AFTER power-on) -------------
    fb.fill(0)
    motor_power_widget = MotorPowerWidget(fb, LCD_W, LCD_H)
    battery_soc_widget = BatterySOCWidget(fb, LCD_W, LCD_H)
    battery_soc_widget.draw_contour()
    lcd.display.show()

    # --------- State trackers ---------
    battery_soc_prev = 9999
    motor_power_prev = 9999
    wheel_speed_prev = 9999
    brakes_prev = False
    vesc_fault_prev = 9999

    t_buttons = time.ticks_ms()
    t_display = time.ticks_ms()
    t_comm = time.ticks_ms()

    # Time/RTC trackers
    t_time_tick = time.ticks_ms()
    t_rtc_try_update_once = time.ticks_ms()
    update_date_time_once = False

    # Main loop
    while True:
        now_ms = time.ticks_ms()

        # UI ~10 Hz
        if time.ticks_diff(now_ms, t_display) > 100:
            t_display = now_ms

            # Battery
            vars.battery_soc_x1000 = 1000
            if battery_soc_prev != vars.battery_soc_x1000:
                battery_soc_prev = vars.battery_soc_x1000
                battery_soc_widget.update(int(vars.battery_soc_x1000/10))

            # Motor power
            vars.motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x10) / 100.0)
            if motor_power_prev != vars.motor_power:
                motor_power_prev = vars.motor_power
                motor_power = filter_motor_power(vars.motor_power)
                
                # max battery current  at high speeds is set to 15A rear motor + 12.5A front motor --> ~2000W @ 72V
                motor_power_percent = map_range(motor_power, 0, 2000, 0, 100, clamp=True)
                motor_power_widget.update(motor_power_percent)

            # Wheel speed
            if wheel_speed_prev != vars.wheel_speed_x10:
                wheel_speed_prev = vars.wheel_speed_x10
                wheel_speed_widget.update(int(vars.wheel_speed_x10 / 10))

            lcd.display.show()

        # ESP-NOW ~6-7 Hz
        if time.ticks_diff(now_ms, t_comm) > 150:
            t_comm = now_ms
            await motor.send_data_async()
            motor.receive_process_data()

            if brakes_prev != vars.brakes_are_active:
                brakes_prev = vars.brakes_are_active
                warning_widget.update("brakes" if vars.brakes_are_active else "")
                lcd.display.show()
            elif vesc_fault_prev != vars.vesc_fault_code:
                vesc_fault_prev = vars.vesc_fault_code
                warning_widget.update("" if not vars.vesc_fault_code else "mot e: %d" % vars.vesc_fault_code)
                lcd.display.show()

        # Buttons ~20 Hz
        if time.ticks_diff(now_ms, t_buttons) > 50:
            t_buttons = now_ms
            for i in range(len(buttons)):
                buttons[i].tick()

        # -------- RTC: try NTP once after ~2s --------
        if (not update_date_time_once) and time.ticks_diff(now_ms, t_rtc_try_update_once) > 2000:
            update_date_time_once = True
            try:
                rtc.update_date_time_from_wifi_ntp()
            except Exception as ex:
                print(ex)

        # -------- Time draw (1 Hz) --------
        if time.ticks_diff(now_ms, t_time_tick) > 1000:
            t_time_tick = now_ms
            try:
                dt = rtc.date_time()
                h, m = dt[3], dt[4]
                if h < 10:
                    time_str = '{:01d}:{:02d}'.format(h, m)
                else:
                    time_str = '{:02d}:{:02d}'.format(h, m)
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
