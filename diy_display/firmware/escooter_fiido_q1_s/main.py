# main.py — MicroPython DISPLAY main (ESP32/ESP32-C3) with aioespnow + FreeSans fonts

import time
import network
import uasyncio as asyncio
import aioespnow

from display_st7565 import Display
from writer import Writer
from fonts import freesans10
from fonts import freesans20
from fonts import freesansbold50
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from battery_soc_widget import BatterySOCWidget
from motor_power_widget import MotorPowerWidget
from widget_wheel_speed import WidgetWheelSpeed
from widget_warning import WidgetWarning
from widget_clock import WidgetClock

import vars as Vars
import firmware_common.thisbutton as tb

# ---------------- Config ----------------
my_mac_address = b"\x00\xb6\xb3\x01\xf7\xf3"
mac_address_motor_board = b"\x00\xb6\xb3\x01\xf7\xf2"

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

def font_text_width(font, s):
    w = 0
    for ch in s:
        _, _, cw = font.get_ch(ch)
        w += cw
    return w

def fit_right(font, s, maxw):
    # Trim from left until it fits in maxw
    while s and font_text_width(font, s) > maxw:
        s = s[1:]
    return s

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
    lcd = Display(
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

    # Writers / Widgets
    writer_small = Writer(fb, freesans20, verbose=False)
    writer_small.set_clip(row_clip=True, col_clip=True, wrap=False)
    
    wheel_speed_widget = WidgetWheelSpeed(fb, LCD_W, LCD_H, font=freesansbold50)
    warning_widget = WidgetWarning(fb, LCD_W, LCD_H, x0=0, y0=39, fg=1, bg=0, font=freesans10, baseline_adjust=0)
    clock_widget = WidgetClock(
        fb, LCD_W, LCD_H,
        font=freesans20,
        x_offset=0,          # caixa agarrada ao canto
        y_offset=0,
        baseline_adjust=3,   # ↓ empurra a linha de base
        top_nudge=0          # ↓ afina dentro da caixa
    )

    # Boot banner (centered, FreeSans20)
    def draw_centered_lines(line1, line2):
        fb.fill(0)
        h = freesans20.height()
        gap = 8
        w1 = font_text_width(freesans20, line1)
        w2 = font_text_width(freesans20, line2)
        total_h = 2*h + gap
        y0 = (LCD_H - total_h)//2
        x1 = (LCD_W - w1)//2
        x2 = (LCD_W - w2)//2
        Writer.set_textpos(fb, y0, x1); writer_small.printstring(line1)
        Writer.set_textpos(fb, y0 + h + gap, x2); writer_small.printstring(line2)
        lcd.display.show()

    draw_centered_lines("Ready to", "POWER ON")

    # Buttons
    nr_buttons = len(BUTTON_PINS)
    button_POWER, button_LEFT, button_RIGHT = range(nr_buttons)

    async def turn_off_execute():
        await motor.send_data_async()
        vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024

    async def turn_off():
        vars.motor_enable_state = False
        draw_centered_lines("Ready to", "POWER OFF")
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
        btn = tb.thisButton(pin, True)
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

    # Main screen (widgets)
    fb.fill(0)
    motor_power_widget = MotorPowerWidget(fb, LCD_W, LCD_H)
    motor_power_widget.draw_contour()
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
    date_time_updated = None  # None=unknown, True=good, False=failed

    # Dummies (for standalone demo)
    power_dummy = 0
    speed_dummy = 0
    battery_dummy = 0

    # Main loop
    while True:
        now_ms = time.ticks_ms()

        # UI ~10 Hz
        if time.ticks_diff(now_ms, t_display) > 100:
            t_display = now_ms

            # Battery (demo spinner here; replace with real values)
            battery_soc_prev = -1
            vars.battery_soc_x1000 = 1000
            if battery_soc_prev != vars.battery_soc_x1000:
                battery_soc_prev = vars.battery_soc_x1000
                battery_soc_widget.update(int(vars.battery_soc_x1000/10))
                # demo spin
                battery_dummy = (battery_dummy + 1) % 100
                battery_soc_widget.update(battery_dummy)

            # Motor power
            vars.motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x10) / 100.0)
            motor_power_prev = -1
            if motor_power_prev != vars.motor_power:
                motor_power_prev = vars.motor_power
                mp = filter_motor_power(vars.motor_power)
                # motor_power_widget.update(int((mp * 100) / 400.0))
                # demo spin
                power_dummy = (power_dummy + 5) % 101
                motor_power_widget.update(power_dummy)

            # Wheel speed
            wheel_speed_prev = -1
            if wheel_speed_prev != vars.wheel_speed_x10:
                wheel_speed_prev = vars.wheel_speed_x10
                # real: wheel_speed_widget.update(int(vars.wheel_speed_x10 / 10))
                # demo spin
                speed_dummy = (speed_dummy + 1) % 100
                wheel_speed_widget.update(speed_dummy)

            lcd.display.show()

        # ESP-NOW ~6-7 Hz
        if time.ticks_diff(now_ms, t_comm) > 150:
            t_comm = now_ms
            await motor.send_data_async()
            motor.receive_process_data()

            # Warnings (demo values here)
            brakes_prev = -1
            vars.brakes_are_active = True  # demo
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
                date_time_updated = rtc.update_date_time_from_wifi_ntp()  # returns True/False
            except Exception:
                date_time_updated = False  # follow original behavior: only try once

        # -------- Time draw (1 Hz) --------
        if time.ticks_diff(now_ms, t_time_tick) > 1000:
            t_time_tick = now_ms
            try:
                dt = rtc.date_time()  # tuple
                clock_widget.update_from_tuple(dt, valid=date_time_updated)  # clears if not synced
                lcd.display.show()    # <-- push buffer after drawing the clock
            except Exception as ex:
                clock_widget.update(valid=False)
                lcd.display.show()    # also push the clear
                print(ex)

        await asyncio.sleep_ms(10)

# Entry
try:
    asyncio.run(main())
finally:
    pass
