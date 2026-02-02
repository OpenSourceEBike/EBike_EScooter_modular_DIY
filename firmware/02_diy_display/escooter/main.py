import time
import network
import uasyncio as asyncio
import machine

from lcd.lcd_st7565 import LCD
from rtc_datetime import RTCDateTime
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

sta, esp = espnow_init(channel=1, local_mac=cfg.mac_address_display)
ap = network.WLAN(network.AP_IF)

power_switch_peer_mac = bytes(cfg.mac_address_power_switch)
motor_peer_mac = bytes(cfg.mac_address_motor_board)
lights_peer_mac = bytes(cfg.mac_address_lights)

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

motor_rx_comms = ESPNowComms(esp, decoder=decode_display_message)
power_switch_tx_comms = ESPNowComms(esp, encoder=encode_power_switch_message)
motor_tx_comms = ESPNowComms(esp, encoder=encode_display_message)
lights_tx_comms = ESPNowComms(esp, encoder=encode_lights_message)

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
      motor_tx_comms.send_data(motor_peer_mac)
      power_switch_tx_comms.send_data(power_switch_peer_mac)
      lights_tx_comms.send_data(lights_peer_mac)
    except Exception as ex:
      print("send_all_off_once err:", ex)

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

async def main_task(vars):
  global screen_manager
  
  motor_power_previous = 0
  time_counter_next = time.ticks_add(time.ticks_ms(), 1000)
  update_date_time_once = False
  time_rtc_try_update_at = None
  first_transition_to_main_screen = False
  period_ms = 50
  next_wake = time.ticks_ms()

  while True:
    now = time.ticks_ms()
    
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

    # Time
    if not first_transition_to_main_screen and \
      screen_manager.current_is(ScreenID.MAIN):
      first_transition_to_main_screen = True
      time_rtc_try_update_at = time.ticks_add(now, 5000)
    
    # Try NTP once after ~5s
    if not update_date_time_once and \
      cfg.enable_rtc_time and \
      screen_manager.current_is(ScreenID.MAIN) and \
      time_rtc_try_update_at is not None and \
      time.ticks_diff(now, time_rtc_try_update_at) >= 0:
      update_date_time_once = True
      try:
        vars.rtc.update_date_time_from_wifi_ntp()
      except Exception as ex:
        print(ex)
        
    # Time draw (1 Hz)
    if cfg.enable_rtc_time and time.ticks_diff(now, time_counter_next) >= 0:
      time_counter_next = time.ticks_add(time_counter_next, 1000)
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
      vars.lights_board_pins_state = 0
      await power_off_forever()  # never returns
    
    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def motor_rx_task(vars):
  period_ms = 50
  next_wake = time.ticks_ms()
  
  while True:
    msg = motor_rx_comms.get_data()
    if msg is not None and len(msg) == 9 and msg[0] == COMMAND_ID_DISPLAY_1:
      vars.battery_voltage_x10   = msg[1]
      vars.battery_current_x10   = msg[2]
      vars.battery_soc_x1000     = msg[3]
      vars.motor_current_x10     = msg[4]
      vars.wheel_speed_x10       = msg[5]
      if vars.wheel_speed_x10 < 0:
        vars.wheel_speed_x10 = 0
      flags = msg[6]
      vars.brakes_are_active       = bool(flags & (1 << 0))
      vars.regen_braking_is_active = bool(flags & (1 << 1))
      vars.battery_is_charging     = bool(flags & (1 << 2))
      vars.mode = (flags >> 3) & 0x07
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
    motor_tx_comms.send_data(motor_peer_mac)
    
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
    if screen_manager.current_is(ScreenID.MAIN):
      # Head/Tail with main lights_state
      if vars.lights_state:
        vars.lights_board_pins_state |= FRONT_LOW_BIT
        vars.lights_board_pins_state |= REAR_TAIL_BIT
      else:
        vars.lights_board_pins_state &= ~FRONT_LOW_BIT
        vars.lights_board_pins_state &= ~REAR_TAIL_BIT

      # Brake light is controlled by the motor main board
      vars.lights_board_pins_state &= ~REAR_BRAKE_BIT
    else:
      vars.lights_board_pins_state = 0

    lights_tx_comms.send_data(lights_peer_mac)

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
