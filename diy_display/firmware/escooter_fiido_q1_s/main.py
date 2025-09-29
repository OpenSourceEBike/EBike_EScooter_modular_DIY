# main.py  — MicroPython DISPLAY main (ESP32 / ESP32-C3) with aioespnow

import time
import network
import uasyncio as asyncio
import aioespnow

# Your modules
from display import Display
from rtc_datetime import RTCDateTime
from escooter_fiido_q1_s.motor_board_espnow import MotorBoard
from battery_soc_widget import BatterySOCWidget, WHITE, BLACK
from motor_power_widget import MotorPowerWidget
import vars as Vars
import firmware_common.thisbutton as tb

########################################
# CONFIGURATIONS

my_mac_address = b"\x00\xb6\xb3\x01\xf7\xf3"
mac_address_motor_board = b"\x00\xb6\xb3\x01\xf7\xf2"

LCD_W, LCD_H = 128, 64
ESP_CHANNEL = 1

# Button pins (adjust to your board)
BTN_POWER = 0
BTN_LEFT  = 1
BTN_RIGHT = 2
BUTTON_PINS = [5, 6, 7]  # POWER, LEFT, RIGHT

# ---------- text helpers ----------
def draw_text(fb, txt, x, y, color=1):
    fb.text(txt, x, y, color)

def draw_text_scaled(fb, txt, x, y, scale=1, color=1, bg=0):
    if scale <= 1:
        fb.text(txt, x, y, color)
        return
    import framebuf
    w = 8 * len(txt)
    h = 8
    buf = bytearray(w * h)
    tmp = framebuf.FrameBuffer(buf, w, h, framebuf.MONO_HLSB)
    tmp.fill(0)
    tmp.text(txt, 0, 0, 1)
    for yy in range(h):
        row = yy * w
        for xx in range(w):
            on = buf[row + xx] != 0
            if on or bg is not None:
                c = color if on else bg
                fb.fill_rect(x + xx * scale, y + yy * scale, scale, scale, c)

def draw_text_right(fb, txt, x_right, y, scale=1, color=1, bg=None):
    w = 8 * len(txt) * scale
    draw_text_scaled(fb, txt, x_right - w, y, scale, color, bg)

# ---------- filter ----------
def filter_motor_power(motor_power):
    if motor_power < 0:
        if motor_power > -10: motor_power = 0
        elif motor_power > -25: pass
        elif motor_power > -50: motor_power = round(motor_power / 2) * 2
        elif motor_power > -100: motor_power = round(motor_power / 5) * 5
        else: motor_power = round(motor_power / 10) * 10
    else:
        if motor_power < 10: motor_power = 0
        elif motor_power < 25: pass
        elif motor_power < 50: motor_power = round(motor_power / 2) * 2
        elif motor_power < 100: motor_power = round(motor_power / 5) * 5
        else: motor_power = round(motor_power / 10) * 10
    return motor_power

async def main():
    print("Starting Display")

    vars = Vars.Vars()

    # ---- Wi-Fi STA (ESP-NOW) ----
    sta = network.WLAN(network.STA_IF)
    if not sta.active():
        sta.active(True)
    try:
        sta.config(mac=my_mac_address)
    except Exception:
        pass
    try:
        try: sta.disconnect()
        except Exception: pass
        sta.config(channel=ESP_CHANNEL)
    except Exception:
        pass
    try:
        ap = network.WLAN(network.AP_IF)
        if ap.active():
            ap.active(False)
    except Exception:
        pass

    # ---- ESP-NOW (aio) ----
    esp = aioespnow.AIOESPNow()
    esp.active(True)
    motor = MotorBoard(esp, mac_address_motor_board, vars)
    await motor.start()  # keep RX loop alive

    # ---- LCD ----
    lcd = Display(
        spi_clk_pin=3, spi_mosi_pin=4, chip_select_pin=1,
        command_pin=2, reset_pin=0, backlight_pin=21,
        spi_clock_frequency=10_000_000,
    )
    lcd.backlight_pwm(0.5)
    fb = lcd.display
    fb.fill(0)
    lcd.display.show()

    # ---- RTC (optional) ----
    rtc = RTCDateTime(rtc_scl_pin=9, rtc_sda_pin=8)

    # ---- Boot banner ----
    fb.fill(0)
    draw_text_scaled(fb, "Ready to", 16, 16, scale=2, color=1, bg=0)
    draw_text_scaled(fb, "POWER ON", 8, 36, scale=2, color=1, bg=0)
    lcd.display.show()

    # ---- Buttons ----
    nr_buttons = len(BUTTON_PINS)
    button_POWER, button_LEFT, button_RIGHT = range(nr_buttons)

    async def turn_off_execute():
        await motor.send_data_async()
        vars.display_communication_counter = (vars.display_communication_counter + 1) % 1024

    async def turn_off():
        vars.motor_enable_state = False
        fb.fill(0)
        draw_text_scaled(fb, "Ready to", 18, 16, scale=2, color=1, bg=0)
        draw_text_scaled(fb, "POWER OFF", 2, 36, scale=2, color=1, bg=0)
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

    buttons = [None] * nr_buttons
    for i, pin in enumerate(BUTTON_PINS):
        btn = tb.thisButton(pin, True)
        btn.setDebounceThreshold(50)
        btn.setLongPressThreshold(1500)
        if 'click_start' in buttons_callbacks[i]: btn.assignClickStart(buttons_callbacks[i]['click_start'])
        if 'click_release' in buttons_callbacks[i]: btn.assignClickRelease(buttons_callbacks[i]['click_release'])
        if 'long_click_start' in buttons_callbacks[i]: btn.assignLongClickStart(buttons_callbacks[i]['long_click_start'])
        if 'long_click_release' in buttons_callbacks[i]: btn.assignLongClickRelease(buttons_callbacks[i]['long_click_release'])
        buttons[i] = btn

    # ---- Main screen ----
    vars.motor_enable_state = True
    vars.buttons_state = 0

    fb.fill(0)
    motor_power_widget = MotorPowerWidget(fb, LCD_W, LCD_H)
    motor_power_widget.draw_contour()
    battery_soc_widget = BatterySOCWidget(fb, LCD_W, LCD_H)
    battery_soc_widget.draw_contour()
    lcd.display.show()

    def draw_speed(value_int):
        fb.fill_rect(70, 0, 58, 48, 0)
        draw_text_right(fb, str(value_int), 127, 0, scale=6, color=1, bg=0)

    def draw_time(hh, mm):
        fb.fill_rect(80, 48, 48, 16, 0)
        draw_text_right(fb, "%02d:%02d" % (hh, mm), 127, 48, scale=2, color=1, bg=0)

    def draw_warning(msg: str):
        fb.fill_rect(0, 37, 80, 16, 0)
        if msg:
            draw_text(fb, msg, 0, 40, 1)

    # ---- State trackers ----
    battery_soc_prev = 9999
    motor_power_prev = 9999
    wheel_speed_prev = 9999
    brakes_prev = False
    vesc_fault_prev = 9999

    t_buttons = time.ticks_ms()
    t_display = time.ticks_ms()
    t_comm = time.ticks_ms()
    # Optional RTC:
    # t_ntp = time.ticks_ms(); did_ntp = False; t_clock = time.ticks_ms()

    # ---- Main loop ----
    while True:
        now_ms = time.ticks_ms()

        # UI ~10 Hz
        if time.ticks_diff(now_ms, t_display) > 100:
            t_display = now_ms

            if battery_soc_prev != vars.battery_soc_x1000:
                battery_soc_prev = vars.battery_soc_x1000
                battery_soc_widget.update(int(vars.battery_soc_x1000 / 10))

            battery_current_x10 = getattr(vars, "battery_current_x10", 0)
            vars.motor_power = int((vars.battery_voltage_x10 * battery_current_x10) / 100.0)
            if motor_power_prev != vars.motor_power:
                motor_power_prev = vars.motor_power
                mp = filter_motor_power(vars.motor_power)
                motor_power_percent = int((mp * 100) / 400.0)
                motor_power_widget.update(motor_power_percent)

            if wheel_speed_prev != vars.wheel_speed_x10:
                wheel_speed_prev = vars.wheel_speed_x10
                draw_speed(int(vars.wheel_speed_x10 / 10.0))

            lcd.display.show()

        # ESP-NOW comms ~6-7 Hz
        if time.ticks_diff(now_ms, t_comm) > 150:
            t_comm = now_ms
            await motor.send_data_async()   # <— await!
            motor.receive_process_data()

            if brakes_prev != vars.brakes_are_active:
                brakes_prev = vars.brakes_are_active
                draw_warning("brakes" if vars.brakes_are_active else "")
                lcd.display.show()
            elif vesc_fault_prev != vars.vesc_fault_code:
                vesc_fault_prev = vars.vesc_fault_code
                draw_warning("" if not vars.vesc_fault_code else "mot e: %d" % (vars.vesc_fault_code,))
                lcd.display.show()

        # Buttons ~20 Hz
        if time.ticks_diff(now_ms, t_buttons) > 50:
            t_buttons = now_ms
            for i in range(nr_buttons):
                buttons[i].tick()

        # Optional RTC (uncomment if you want it)
        # if not did_ntp and time.ticks_diff(now_ms, t_ntp) > 2000:
        #     did_ntp = True
        #     rtc.update_datetime_from_wifi_ntp()
        # if time.ticks_diff(now_ms, t_clock) > 1000:
        #     t_clock = now
        #     dt = rtc.datetime()
        #     draw_time(dt[3], dt[4]); lcd.display.show()

        await asyncio.sleep_ms(10)  # keep loop alive for aioespnow

# ---- Entry point ----
try:
    asyncio.run(main())
finally:
    pass
