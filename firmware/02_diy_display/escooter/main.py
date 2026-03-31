import time
import network
import uasyncio as asyncio
import machine
from machine import WDT

from lcd.lcd_st7565 import LCD
from rtc_datetime import RTCDateTime
from wifi_time_sync import sync_rtc_time_from_wifi_ntp_async
from common.thisbutton import thisButton
from common.utils import map_range
from common.lights_bits import FRONT_LOW_BIT, REAR_TAIL_BIT, REAR_BRAKE_BIT, IO_BITS_MASK
from screen_manager import ScreenManager, ScreenID
import vars as Vars
import common.config_runtime as cfg
from common.espnow import espnow_init, ESPNowComms
 
from common.espnow_commands import COMMAND_ID_DISPLAY_1, COMMAND_ID_POWER_SWITCH_1

print("Starting Display")

vars = Vars.Vars()

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
system_boot_ms = time.ticks_ms()
fb.fill(0)
fb.text("Ready", 44, 28, 1)
fb.show()

screen_manager = ScreenManager(fb, vars)
screen_manager.render(vars)

# Hardware watchdog: reset the board if not fed within 30 seconds
wdt = WDT(timeout=30000) # timeout in milliseconds

if cfg.enable_rtc_time:
  vars.rtc = RTCDateTime(
    rtc_scl_pin=cfg.rtc_scl_pin,
    rtc_sda_pin=cfg.rtc_sda_pin,
    timezone_name=cfg.rtc_timezone,
    debug=cfg.rtc_debug,
  )

BUTTON_PINS = [
  cfg.power_button_pin,
  cfg.lights_button_pin
  ]

nr_buttons = len(BUTTON_PINS)
button_POWER, button_LIGHTS = range(nr_buttons)
BACKLIGHT_ON_BRIGHTNESS = 0.5
backlight_is_on = True

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

def update_time_string(vars):
  try:
    dt = vars.rtc.date_time()
    hour, minute = dt[3], dt[4]
    vars.time_string = ('{:01d}:{:02d}' if hour < 10 else '{:02d}:{:02d}').format(hour, minute)
  except Exception as ex:
    vars.time_string = ''
    print(ex)

def update_auto_lights_state(vars):
  previous_auto_lights_state = bool(vars.auto_lights_state)
  vars.auto_lights_state = False

  if not cfg.enable_rtc_time or not getattr(cfg, 'auto_lights_schedule_enabled', False):
    return

  try:
    dt = vars.rtc.date_time()
    now_minutes = (int(dt[3]) * 60) + int(dt[4])
    on_minutes = (int(cfg.auto_lights_on_hour) * 60) + int(cfg.auto_lights_on_minute)
    off_minutes = (int(cfg.auto_lights_off_hour) * 60) + int(cfg.auto_lights_off_minute)

    if on_minutes == off_minutes:
      vars.auto_lights_state = False
    elif on_minutes < off_minutes:
      vars.auto_lights_state = on_minutes <= now_minutes < off_minutes
    else:
      vars.auto_lights_state = now_minutes >= on_minutes or now_minutes < off_minutes
  except Exception as ex:
    print(ex)
    return

  if vars.auto_lights_state != previous_auto_lights_state:
    vars.lights_state = vars.auto_lights_state

def effective_lights_state(vars):
  return bool(vars.lights_state)

def set_backlight_enabled(enabled):
  global backlight_is_on
  enabled = bool(enabled)
  if backlight_is_on == enabled:
    return
  backlight_is_on = enabled
  lcd.backlight_pwm(BACKLIGHT_ON_BRIGHTNESS if enabled else 0.0)

if cfg.enable_rtc_time:
  vars.rtc.update_internal_rtc_from_external()
  update_time_string(vars)
  update_auto_lights_state(vars)

def encode_power_switch_message():
  turn_off_relay = 1 if vars.turn_off_relay else 0
  return f"{COMMAND_ID_POWER_SWITCH_1} {turn_off_relay}".encode("ascii")

def encode_display_message():
  motor_enable_state = 1 if vars.motor_enable_state else 0
  return f"{COMMAND_ID_DISPLAY_1} {motor_enable_state} {vars.buttons_state}".encode("ascii")

def decode_display_message(msg):
  parts = [int(s) for s in msg.decode("ascii").split()]
  if len(parts) == 9 and parts[0] == COMMAND_ID_DISPLAY_1:
    return parts
  return None

def encode_lights_message():
  pins_state = int(vars.lights_board_pins_state)
  mask = IO_BITS_MASK & ~REAR_BRAKE_BIT
  return f"{COMMAND_ID_DISPLAY_1} {mask} {pins_state}".encode("ascii")

def init_espnow_stack():
  global sta, ap, esp
  global power_switch_tx_comms, motor_rx_comms, motor_tx_comms, lights_tx_comms

  sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_display)
  ap = network.WLAN(network.AP_IF)

  power_switch_tx_comms = ESPNowComms(
    esp,
    bytes(cfg.mac_address_power_switch),
    encoder=encode_power_switch_message)

  motor_rx_comms = ESPNowComms(
    esp,
    bytes(cfg.mac_address_motor_board),
    decoder=decode_display_message)

  motor_tx_comms = ESPNowComms(
    esp,
    bytes(cfg.mac_address_motor_board),
    encoder=encode_display_message)

  lights_tx_comms = ESPNowComms(
    esp,
    bytes(cfg.mac_address_lights),
    encoder=encode_lights_message)

# ESPNow wireless communications
init_espnow_stack()

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

async def power_off_forever(backlight_timeout_ms):
  """
  Block forever: keep OFF states latched and only poll POWER to allow a hard reset.
  Any change on POWER bit (0x0100) triggers machine.reset().
  """
  buttons_state_previous = bool(vars.buttons_state & 0x0100)
  backlight_idle_since = time.ticks_ms()
  while True:
    # Keep button state fresh so the same wake conditions still apply while powering off.
    for i in range(len(vars.buttons)):
      vars.buttons[i].tick()

    current = bool(vars.buttons_state & 0x0100)
    if current != buttons_state_previous:
      machine.reset()

    now = time.ticks_ms()
    wake_backlight = (
      vars.brakes_are_active or
      bool(vars.buttons_state & 0x0100) or
      vars.motor_current_x10 > 10 or
      vars.wheel_speed_x10 != 0
    )

    if wake_backlight:
      backlight_idle_since = now
      set_backlight_enabled(True)
    elif time.ticks_diff(now, backlight_idle_since) >= backlight_timeout_ms:
      set_backlight_enabled(False)

    try:
      # Ensure desired OFF states are in vars before calling this
      motor_tx_comms.send_data()
      power_switch_tx_comms.send_data()
      lights_tx_comms.send_data()
    except Exception as ex:
      print("send_all_off_once err:", ex)

    # Keep the watchdog alive while staying in the OFF state
    wdt.feed()

    await asyncio.sleep_ms(100)

async def ui_task(fb, lcd, vars):
  global screen_manager
  
  # Main screen takes about 80ms to update
  period_ms = 100
  next_wake = time.ticks_ms()
  
  while True:
    screen_manager.update(vars)
    screen_manager.render(vars)
    lcd.show()
  
    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def rtc_sync_task(vars, delay_ms=2000):
  await asyncio.sleep_ms(delay_ms)
  vars.comms_paused = True
  try:
    await sync_rtc_time_from_wifi_ntp_async(
      vars.rtc,
      wifi_timeout_s=cfg.rtc_wifi_timeout_s,
      ntp_timeout_s=cfg.rtc_ntp_timeout_s,
    )
    update_time_string(vars)
    if not getattr(cfg, 'auto_lights_schedule_enabled_at_boot_only', False):
      update_auto_lights_state(vars)
  except Exception as ex:
    print(ex)
  finally:
    init_espnow_stack()
    await asyncio.sleep_ms(300)
    vars.comms_paused = False

async def main_task(vars):
  global screen_manager
  
  motor_power_previous = 0
  rtc_sync_started = False
  was_in_main_screen = screen_manager.current_is(ScreenID.MAIN)
  time_counter_next = time.ticks_add(time.ticks_ms(), 1000)
  backlight_timeout_ms = getattr(cfg, 'backlight_timeout_ms', 1000)
  backlight_idle_since = system_boot_ms
  main_screen_timeout_ms = getattr(cfg, 'main_screen_timeout_ms', 300000)
  main_screen_idle_since = time.ticks_ms()
  period_ms = 50
  next_wake = time.ticks_ms()
  set_backlight_enabled(True)

  while True:
    now = time.ticks_ms()
    in_main_screen = screen_manager.current_is(ScreenID.MAIN)

    if cfg.enable_rtc_time and in_main_screen and not was_in_main_screen and not rtc_sync_started:
      rtc_sync_started = True
      asyncio.create_task(rtc_sync_task(vars, delay_ms=cfg.rtc_sync_delay_ms))
    was_in_main_screen = in_main_screen
    
    # Motor power
    motor_power = int((vars.battery_voltage_x10 * vars.battery_current_x10) / 100.0)
    if motor_power_previous != motor_power:
      motor_power_previous = motor_power
      motor_power = filter_motor_power(motor_power)
      if motor_power >= 0:
        vars.motor_power_percent = map_range(
          motor_power, 0, cfg.motor_power_max_w, 0, 100, clamp=True
        )
      else:
        vars.motor_power_percent = map_range(
          motor_power, 0, cfg.motor_regen_power_max_w, 0, -100, clamp=True
        )

    # Buttons
    for i in range(len(vars.buttons)):
      vars.buttons[i].tick()

    in_idle_screen = (
      screen_manager.current_is(ScreenID.BOOT) or
      screen_manager.current_is(ScreenID.CHARGING) or
      screen_manager.current_is(ScreenID.POWEROFF)
    )
    wake_backlight = (
      vars.brakes_are_active or
      bool(vars.buttons_state & 0x0100) or
      vars.motor_current_x10 > 10 or
      vars.wheel_speed_x10 != 0
    )
    main_screen_active = (
      wake_backlight or
      vars.wheel_speed_x10 != 0
    )

    if not in_idle_screen:
      backlight_idle_since = now
      set_backlight_enabled(True)
    else:
      if wake_backlight:
        backlight_idle_since = now
        set_backlight_enabled(True)
      elif time.ticks_diff(now, backlight_idle_since) >= backlight_timeout_ms:
        set_backlight_enabled(False)

    if in_main_screen:
      if main_screen_active:
        main_screen_idle_since = now
      elif time.ticks_diff(now, main_screen_idle_since) >= main_screen_timeout_ms:
        vars.motor_enable_state = False
        screen_manager.force(ScreenID.BOOT)
        main_screen_idle_since = now
    else:
      main_screen_idle_since = now

    # Time draw (1 Hz)
    if cfg.enable_rtc_time and time.ticks_diff(now, time_counter_next) >= 0:
      time_counter_next = time.ticks_add(time_counter_next, 1000)
      update_time_string(vars)
      if not getattr(cfg, 'auto_lights_schedule_enabled_at_boot_only', False):
        update_auto_lights_state(vars)

    # Shutdown
    if vars.shutdown_request:
      vars.turn_off_relay = True
      vars.motor_enable_state = False
      vars.lights_board_pins_state = 0
      await power_off_forever(backlight_timeout_ms)  # never returns
    
    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

    # Feed the hardware watchdog regularly
    wdt.feed()

async def motor_rx_task(vars):
  period_ms = 50
  next_wake = time.ticks_ms()
  
  while True:
    if vars.comms_paused:
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      if remaining > 0:
        await asyncio.sleep_ms(remaining)
      else:
        await asyncio.sleep_ms(0)
      continue

    msg = motor_rx_comms.get_data()
    if msg is not None and len(msg) == 9 and msg[0] == COMMAND_ID_DISPLAY_1:
      vars.battery_voltage_x10   = msg[1]
      vars.battery_current_x10   = msg[2]
      vars.battery_soc_x1000     = msg[3]
      vars.motor_current_x10     = msg[4]
      vars.wheel_speed_x10       = msg[5]
      flags = msg[6]
      vars.brakes_are_active       = bool(flags & (1 << 0))
      vars.regen_braking_is_active = bool(flags & (1 << 1))
      vars.battery_is_charging     = bool(flags & (1 << 2))
      vars.mode = (flags >> 3) & 0x07
      vars.cruise_control_is_active = bool(flags & (1 << 6))
      vars.vesc_temperature_x10  = msg[7]
      vars.motor_temperature_x10 = msg[8]
    
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def motor_tx_task(vars):
  period_ms = 100
  next_wake = time.ticks_ms()
  while True:
    if vars.comms_paused:
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      if remaining > 0:
        await asyncio.sleep_ms(remaining)
      else:
        await asyncio.sleep_ms(0)
      continue

    motor_tx_comms.send_data()
    
    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def lights_task(vars):
  global screen_manager
  period_ms = 50
  next_wake = time.ticks_ms()
  
  while True:
    if vars.comms_paused:
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      if remaining > 0:
        await asyncio.sleep_ms(remaining)
      else:
        await asyncio.sleep_ms(0)
      continue

    if screen_manager.current_is(ScreenID.MAIN):
      # The display decides the requested head/tail state; the lights board only applies it.
      lights_requested = effective_lights_state(vars)
      tail_enabled = (lights_requested or cfg.tail_always_enabled) and vars.motor_enable_state
      head_enabled = lights_requested and vars.motor_enable_state

      if head_enabled:
        vars.lights_board_pins_state |= FRONT_LOW_BIT
      else:
        vars.lights_board_pins_state &= ~FRONT_LOW_BIT

      if tail_enabled:
        vars.lights_board_pins_state |= REAR_TAIL_BIT
      else:
        vars.lights_board_pins_state &= ~REAR_TAIL_BIT

      # Brake light is controlled by the motor main board
      vars.lights_board_pins_state &= ~REAR_BRAKE_BIT
    else:
      vars.lights_board_pins_state = 0

    lights_tx_comms.send_data()

    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

# Entry
async def main():    
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
