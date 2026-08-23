import time
_boot_t0 = time.ticks_ms()
from lcd.lcd_st7565 import LCD
import common.config_runtime as cfg

def boot_log(label):
  if cfg.boot_timing_debug:
    elapsed_ms = time.ticks_diff(time.ticks_ms(), _boot_t0)
    print("[boot +{:>5} ms] {}".format(elapsed_ms, label))

boot_log("Starting Display")

lcd = LCD(
  spi_clk_pin=cfg.pin_spi_clk,
  spi_mosi_pin=cfg.pin_spi_mosi,
  chip_select_pin=cfg.pin_cs,
  command_pin=cfg.pin_dc,
  reset_pin=cfg.pin_rst,
  backlight_pin=cfg.pin_bl,
  spi_clock_frequency=cfg.spi_baud,
)
boot_log("LCD initialized")
fb = lcd.display
lcd.backlight_pwm(0.5)
system_boot_ms = time.ticks_ms()
boot_comm_grace_ms = 3000
cfg.system_boot_ms = system_boot_ms
cfg.boot_comm_grace_ms = boot_comm_grace_ms
fb.fill(1)
fb.show()
boot_log("First framebuffer flush")

import network
import uasyncio as asyncio
import machine
import esp32
from common.utils import map_range
from common.config_battery_resistance import (
  battery_resistance_config,
  validate_battery_resistance_display_config,
  validate_battery_resistance_measurement_config,
)
from common.battery_resistance_persistence import (
  load_battery_resistance_history,
  save_battery_resistance_history,
)
from common.lights_bits import FRONT_LOW_BIT, REAR_TAIL_BIT, REAR_BRAKE_BIT, IO_BITS_MASK
import vars as Vars
from common.espnow_protocol import (
  BOARD_DISPLAY,
  BOARD_LIGHTS,
  BOARD_MOTOR,
  BOARD_POWER_SWITCH,
  HEALTH_MOTOR_LIGHTS_TX_OK,
  HEALTH_MOTOR_REAR_SPEED_VALID,
  MSG_COMMAND,
  MSG_STATUS,
  POWER_CONFIG_CMD,
  POWER_SWITCH_CMD,
  build_command,
  parse_frame,
)
from screen_manager import ScreenManager, ScreenID
from common.thisbutton import thisButton
from common.espnow import (
  espnow_init,
  ESPNowComms,
  espnow_recv_all,
  espnow_jittered_period_ms,
  configure_wifi_radio,
)

vars = Vars.Vars()
battery_resistance_display_config_error = validate_battery_resistance_display_config(
  battery_resistance_config)
battery_resistance_measurement_config_error = \
  validate_battery_resistance_measurement_config(battery_resistance_config)
vars.battery_resistance_enabled = battery_resistance_display_config_error is None
vars.battery_resistance_measurement_available = (
  battery_resistance_measurement_config_error is None)
vars.battery_resistance_config_error = (
  battery_resistance_display_config_error or
  battery_resistance_measurement_config_error or
  ''
)
if not vars.battery_resistance_enabled:
  print("Battery resistance display disabled:",
        battery_resistance_display_config_error)
elif not vars.battery_resistance_measurement_available:
  print("Battery resistance measurement unavailable:",
        battery_resistance_measurement_config_error)
boot_log("Vars initialized")

my_mac_address = cfg.mac_address_display
mac_address_motor_board = cfg.mac_address_motor_board
mac_address_lights = cfg.mac_address_lights
mac_address_power_switch = cfg.mac_address_power_switch

ESPNOW_DEBUG = bool(getattr(cfg, "espnow_debug", False))
_sta, _esp = espnow_init(channel=1, local_mac=my_mac_address, debug=ESPNOW_DEBUG)
configure_wifi_radio(_sta, cfg.wifi_tx_power_dbm["display"], "display", debug=ESPNOW_DEBUG)

DISPLAY_LIGHTS_MASK = IO_BITS_MASK & ~REAR_BRAKE_BIT
MOTOR_BOARD_TX_COMM_TIMEOUT_MS = 1500
MOTOR_BOARD_RX_COMM_TIMEOUT_MS = 2000
LIGHTS_BOARD_TX_COMM_TIMEOUT_MS = 1500
LIGHTS_HEARTBEAT_MS = 250
LIGHTS_RETRY_MS = 50
LIGHTS_RETRY_MAX_MS = 1000
POWER_SWITCH_BOARD_COMM_TIMEOUT_MS = 1500
POWER_SWITCH_HEARTBEAT_MS = 250
POWER_CONFIG_RETRY_MS = 2000
RTC_SYNC_DELAY_MS = 2000
# A BMS reconnect can include an 8 s scan plus its first BASIC response.
# Start this timer only after the Wi-Fi/BLE radio handover has completed.
CHARGING_RECONFIRM_TIMEOUT_MS = 20000
_power_peer = bytes(mac_address_power_switch)
_power_peer_added = False
_power_tx_had_failure = False
_power_tx_had_success = False
_last_power_switch_sent = None
_last_power_switch_tx_attempt_ms = 0
_next_power_switch_tx_ms = 0
_last_power_switch_tx_ok_ms = 0
_last_power_config_sent = None
_pending_power_config_snapshot = None
_pending_power_config_attempt_ms = 0
_last_power_config_feedback = None
def _motor_command_signature():
  return (
    int(vars.motor_enable_state),
    int(vars.buttons_state),
    int(effective_lights_state(vars)),
    int(vars.turn_off_relay),
  )

def encode_motor_command():
  return build_command(
    BOARD_DISPLAY,
    BOARD_MOTOR,
    *(_motor_command_signature()),
  )

def decode_motor_status(msg):
  parts = parse_frame(msg)
  if parts is None:
    return None
  if len(parts) >= 14 and parts[0] == MSG_STATUS and parts[1] == BOARD_MOTOR and parts[2] == BOARD_DISPLAY:
    return parts
  return None

def _display_lights_state():
  # Keep rider-visible lights active in MAIN and during the short
  # MOTOR_BLOCKED re-arm warning; motor torque remains independently blocked.
  if (
    not (
      screen_manager.current_is(ScreenID.MAIN) or
      screen_manager.current_is(ScreenID.MOTOR_BLOCKED)
    ) or
    not vars.motor_enable_state
  ):
    return 0

  lights_requested = bool(vars.lights_state)
  tail_enabled = (lights_requested or cfg.tail_always_enabled) and not vars.battery_is_charging
  front_low_enabled = lights_requested

  state = 0
  if front_low_enabled:
    state |= FRONT_LOW_BIT
  if tail_enabled:
    state |= REAR_TAIL_BIT
  return state

def encode_lights_command():
  return build_command(
    BOARD_DISPLAY,
    BOARD_LIGHTS,
    DISPLAY_LIGHTS_MASK,
    _display_lights_state(),
  )

def decode_power_switch_status(msg):
  parts = parse_frame(msg)
  if parts is None:
    return None
  if len(parts) == 9 and parts[0] == MSG_STATUS and parts[1] == BOARD_POWER_SWITCH and parts[2] == BOARD_DISPLAY:
    return parts
  return None

def _ensure_power_peer():
  global _power_peer_added
  if _power_peer_added:
    return True
  try:
    _esp.add_peer(_power_peer)
    _power_peer_added = True
    return True
  except OSError as e:
    if e.args and e.args[0] == -12395:
      _power_peer_added = True
      return True
    if ESPNOW_DEBUG:
      print("ESP-NOW add_peer error:", e)
  except Exception as ex:
    if ESPNOW_DEBUG:
      print("ESP-NOW add_peer error:", ex)
  return False

def _send_power_packet(payload):
  global _power_tx_had_failure, _power_tx_had_success
  if not _ensure_power_peer():
    return False
  try:
    ok = _esp.send(_power_peer, payload)
    if ok is False:
      time.sleep_ms(10)
      ok = _esp.send(_power_peer, payload)
    if ok is False:
      if not _power_tx_had_failure:
        if ESPNOW_DEBUG:
          print("ESP-NOW tx error to peer {}".format(_power_peer))
        _power_tx_had_failure = True
        _power_tx_had_success = False
      return False
    _power_tx_had_failure = False
    if not _power_tx_had_success:
      if ESPNOW_DEBUG:
        print("ESP-NOW tx ok to peer {}".format(_power_peer))
      _power_tx_had_success = True
    return True
  except OSError as e:
    if not (e.args and e.args[0] == 116):
      if ESPNOW_DEBUG:
        print("ESP-NOW tx error:", e)
    return False
  except Exception as e:
    if ESPNOW_DEBUG:
      print("ESP-NOW tx error:", e)
    return False

motor_board = ESPNowComms(
  _esp,
  bytes(mac_address_motor_board),
  decoder=decode_motor_status,
  encoder=encode_motor_command,
  debug=ESPNOW_DEBUG,
)

lights_board = ESPNowComms(
  _esp,
  bytes(mac_address_lights),
  encoder=encode_lights_command,
  debug=ESPNOW_DEBUG,
)
if ESPNOW_DEBUG:
  print("ESP-NOW lights peer MAC:", bytes(mac_address_lights))
  print("ESP-NOW lights peer ready:", lights_board.peer_ready)

# The display owns BMS communication and charging-state detection. BLE scanning
# starts after ESP-NOW startup and is paused during Wi-Fi/NTP synchronization.
bms = None
if cfg.has_jbd_bms:
  import bluetooth
  from bms_jbd import JbdBmsClient

  _ble = bluetooth.BLE()
  bms = JbdBmsClient(
    ble=_ble,
    target_name=cfg.jbd_bms_bluetooth_name,
    query_period_ms=1000,
    interleave_cells=True,
    debug=getattr(cfg, "bms_debug", False),
  )

  async def bms_task(bms, vars):
    period_ms = 50
    next_wake = time.ticks_ms()
    await asyncio.sleep_ms(300)
    while vars.rtc_sync_pending or vars.comms_paused:
      await asyncio.sleep_ms(50)
    bms.start(scan_ms=8000)
    while True:
      bms.tick()
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      await asyncio.sleep_ms(remaining if remaining > 0 else 0)

  async def bms_read_task(bms, vars):
    period_ms = 1000
    next_wake = time.ticks_ms()
    while True:
      if bms.is_connected() and bms.is_basic_fresh(3000):
        vars.bms_battery_current_x100 = bms.get_current_a_x100()
        vars.bms_battery_current_last_update_ms = bms.last_basic_data_ms
      else:
        vars.bms_battery_current_x100 = None
        vars.bms_battery_current_last_update_ms = 0
      next_wake = time.ticks_add(next_wake, period_ms)
      remaining = time.ticks_diff(next_wake, time.ticks_ms())
      await asyncio.sleep_ms(remaining if remaining > 0 else 0)

def _power_config_snapshot():
  return (
    int(cfg.motion_detection_threshold),
    int(cfg.motion_detection_rate_hz),
    int(getattr(cfg, "motion_detection_ac_mode", True)),
    int(cfg.timeout_no_motion_seconds_to_disable_relay),
    int(getattr(cfg, "seconds_to_wait_before_movement_detection", 20)),
  )

def _power_config_payload():
  return " ".join((
    str(int(MSG_COMMAND)),
    str(int(BOARD_DISPLAY)),
    str(int(BOARD_POWER_SWITCH)),
    str(int(POWER_CONFIG_CMD)),
    str(int(cfg.motion_detection_threshold)),
    str(int(cfg.motion_detection_rate_hz)),
    str(int(getattr(cfg, "motion_detection_ac_mode", True))),
    str(int(cfg.timeout_no_motion_seconds_to_disable_relay)),
    str(int(getattr(cfg, "seconds_to_wait_before_movement_detection", 20))),
  )).encode("ascii")

def _send_power_config_if_needed(now, current_power_config):
  global _last_power_config_sent
  global _pending_power_config_snapshot
  global _pending_power_config_attempt_ms

  if current_power_config == _last_power_config_sent:
    _pending_power_config_snapshot = None
    _pending_power_config_attempt_ms = 0
    return True

  if current_power_config != _pending_power_config_snapshot:
    _pending_power_config_snapshot = current_power_config
    _pending_power_config_attempt_ms = 0

  if (
    _pending_power_config_attempt_ms != 0 and
    time.ticks_diff(now, _pending_power_config_attempt_ms) < POWER_CONFIG_RETRY_MS
  ):
    return False

  ok = _send_power_packet(_power_config_payload())
  _pending_power_config_attempt_ms = now
  if ok:
    _last_power_config_sent = current_power_config
    _pending_power_config_snapshot = None
    _pending_power_config_attempt_ms = 0
  return ok

def _rebuild_espnow_stack():
  global _sta, _esp
  global motor_board, lights_board
  global _power_peer_added, _power_tx_had_failure, _power_tx_had_success
  global _last_power_switch_sent, _last_power_switch_tx_attempt_ms, _last_power_switch_tx_ok_ms
  global _next_power_switch_tx_ms
  global _last_power_config_sent
  global _pending_power_config_snapshot, _pending_power_config_attempt_ms

  now = time.ticks_ms()
  vars.motor_board_tx_ok = False
  vars.motor_board_rx_ok = False
  vars.motor_lights_tx_ok = False
  vars.lights_board_comm_ok = False
  vars.power_switch_board_comm_ok = False
  vars.motor_board_tx_last_ok_ms = time.ticks_add(now, -MOTOR_BOARD_TX_COMM_TIMEOUT_MS)
  vars.motor_board_rx_last_ok_ms = time.ticks_add(now, -MOTOR_BOARD_RX_COMM_TIMEOUT_MS)
  vars.lights_board_tx_last_ok_ms = time.ticks_add(now, -LIGHTS_BOARD_TX_COMM_TIMEOUT_MS)

  _sta, _esp = espnow_init(
    channel=1,
    local_mac=my_mac_address,
    debug=ESPNOW_DEBUG,
    strict=True,
  )
  configure_wifi_radio(_sta, cfg.wifi_tx_power_dbm["display"], "display", debug=ESPNOW_DEBUG)

  motor_board = ESPNowComms(
    _esp,
    bytes(mac_address_motor_board),
    decoder=decode_motor_status,
    encoder=encode_motor_command,
    debug=ESPNOW_DEBUG,
  )

  lights_board = ESPNowComms(
    _esp,
    bytes(mac_address_lights),
    encoder=encode_lights_command,
    debug=ESPNOW_DEBUG,
  )

  if not motor_board.peer_ready or not lights_board.peer_ready:
    raise RuntimeError("ESP-NOW peer setup incomplete")

  _power_peer_added = False
  _power_tx_had_failure = False
  _power_tx_had_success = False
  _last_power_switch_sent = None
  _last_power_switch_tx_attempt_ms = 0
  _last_power_switch_tx_ok_ms = 0
  _next_power_switch_tx_ms = 0
  _last_power_config_sent = None
  _last_power_config_feedback = None
  _pending_power_config_snapshot = None
  _pending_power_config_attempt_ms = 0

  if not _ensure_power_peer():
    raise RuntimeError("ESP-NOW power peer setup incomplete")

screen_manager = ScreenManager(fb, vars)
screen_manager.render(vars)
boot_log("Boot screen rendered")

BUTTON_PINS = [
  cfg.power_button_pin,
  cfg.lights_button_pin
  ]

nr_buttons = len(BUTTON_PINS)
button_POWER, button_LIGHTS = range(nr_buttons)
BACKLIGHT_ON_BRIGHTNESS = 0.5
backlight_is_on = True
_rtc_datetime_class = None
_wifi_ntp_sync = None
NVS_NAMESPACE = "diy_display"
NVS_KEY_RTC_NTP_OK = "rtc_ntp_ok"

def get_rtc_datetime_class():
  global _rtc_datetime_class
  if _rtc_datetime_class is None:
    from rtc_datetime import RTCDateTime
    _rtc_datetime_class = RTCDateTime
  return _rtc_datetime_class

async def sync_rtc_time_from_wifi_ntp_async_lazy(*args, **kwargs):
  global _wifi_ntp_sync
  if _wifi_ntp_sync is None:
    from wifi_time_sync import sync_rtc_time_from_wifi_ntp_async
    _wifi_ntp_sync = sync_rtc_time_from_wifi_ntp_async
  return await _wifi_ntp_sync(*args, **kwargs)

def _open_nvs():
  try:
    return esp32.NVS(NVS_NAMESPACE)
  except Exception:
    return None

def load_rtc_ntp_sync_valid():
  nvs = _open_nvs()
  if nvs is None:
    return False
  try:
    return bool(nvs.get_i32(NVS_KEY_RTC_NTP_OK))
  except Exception:
    return False

def save_rtc_ntp_sync_valid(value):
  nvs = _open_nvs()
  if nvs is None:
    return False
  try:
    nvs.set_i32(NVS_KEY_RTC_NTP_OK, 1 if value else 0)
    nvs.commit()
  except Exception:
    return False
  return True

def _battery_resistance_timestamp(vars):
  if not getattr(vars, 'rtc_time_valid', False) or vars.rtc is None:
    return 0
  try:
    dt = vars.rtc.date_time()
    return time.mktime((dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], 0, 0))
  except Exception:
    return 0

def record_battery_resistance_result(vars, resistance_mohm):
  timestamp = _battery_resistance_timestamp(vars)
  vars.battery_resistance_last_mohm = resistance_mohm
  vars.battery_resistance_last_timestamp = timestamp
  save_minimum = (
    vars.battery_resistance_min_mohm is None or
    resistance_mohm < vars.battery_resistance_min_mohm
  )
  save_maximum = (
    vars.battery_resistance_max_mohm is None or
    resistance_mohm > vars.battery_resistance_max_mohm
  )
  if save_minimum:
    vars.battery_resistance_min_mohm = resistance_mohm
    vars.battery_resistance_min_timestamp = timestamp
  if save_maximum:
    vars.battery_resistance_max_mohm = resistance_mohm
    vars.battery_resistance_max_timestamp = timestamp
  vars.battery_resistance_history_dirty = True
  vars.battery_resistance_alert_pending = (
    resistance_mohm,
    int(battery_resistance_config.alert_duration_ms),
  )

if cfg.enable_rtc_time:
  vars.rtc = get_rtc_datetime_class()(
    rtc_scl_pin=cfg.rtc_scl_pin,
    rtc_sda_pin=cfg.rtc_sda_pin,
    timezone_name=cfg.rtc_timezone,
    debug=cfg.rtc_debug,
  )
  boot_log("RTC object initialized")

if vars.battery_resistance_enabled:
  load_battery_resistance_history(vars, battery_resistance_config)

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
  if not getattr(vars, 'rtc_time_valid', False):
    vars.time_string = ''
    return
  try:
    dt = vars.rtc.date_time()
    hour, minute = dt[3], dt[4]
    vars.time_string = ('{:01d}:{:02d}' if hour < 10 else '{:02d}:{:02d}').format(hour, minute)
  except Exception as ex:
    vars.time_string = ''
    print(ex)

def refresh_lights_state(vars):
  schedule_enabled = bool(getattr(cfg, 'auto_lights_schedule_enabled', False))
  schedule_authoritative = bool(
    getattr(cfg, 'auto_lights_schedule_authoritative', False)
  )
  if schedule_enabled and schedule_authoritative:
    vars.lights_state = bool(vars.auto_lights_state)
  else:
    # Default policy: the maintained switch is a manual ON override and the
    # schedule is an additional automatic ON request.
    vars.lights_state = bool(
      getattr(vars, 'lights_switch_state', False) or
      getattr(vars, 'auto_lights_state', False)
    )

def update_auto_lights_state(vars):
  vars.auto_lights_state = False

  if not cfg.enable_rtc_time or not getattr(cfg, 'auto_lights_schedule_enabled', False):
    refresh_lights_state(vars)
    return

  if not getattr(vars, 'rtc_ntp_sync_valid', False):
    refresh_lights_state(vars)
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
    refresh_lights_state(vars)
    return

  refresh_lights_state(vars)

def effective_lights_state(vars):
  return (
    bool(vars.lights_state) and
    bool(vars.motor_enable_state) and
    screen_manager.current_is(ScreenID.MAIN)
  )

def set_backlight_enabled(enabled):
  global backlight_is_on
  enabled = bool(enabled)
  if backlight_is_on == enabled:
    return
  backlight_is_on = enabled
  lcd.backlight_pwm(BACKLIGHT_ON_BRIGHTNESS if enabled else 0.0)

def power_button_is_active():
  return bool(vars.buttons[button_POWER].buttonActive)

if cfg.enable_rtc_time:
  rtc_has_external = vars.rtc.has_external_rtc()
  rtc_ntp_sync_valid_stored = load_rtc_ntp_sync_valid()
  vars.rtc_time_valid = bool(vars.rtc.update_internal_rtc_from_external())
  vars.rtc_ntp_sync_valid = bool(
    rtc_has_external and
    rtc_ntp_sync_valid_stored and
    vars.rtc_time_valid
  )
  update_time_string(vars)
  update_auto_lights_state(vars)
  boot_log("RTC initial sync complete")

# ESPNow wireless communications
boot_log("ESP-NOW stack initialized")

# --- button callbacks ---
def button_power_click_start_cb():
  vars.power_click_pending = True
  vars.buttons_state |= 1
  if vars.buttons_state & 0x0100: vars.buttons_state &= ~0x0100
  else: vars.buttons_state |= 0x0100

def button_power_click_release_cb():
  vars.buttons_state &= ~1

def button_power_long_click_start_cb():
  vars.power_long_click_pending = True
  vars.buttons_state |= 2
  if vars.buttons_state & 0x0200: vars.buttons_state &= ~0x0200
  else: vars.buttons_state |= 0x0200

def button_power_long_click_release_cb():
  vars.buttons_state &= ~2

def button_lights_switch_change_cb(is_on):
  vars.lights_switch_state = bool(is_on)
  refresh_lights_state(vars)

buttons_callbacks = {
  button_POWER: {
    'click_start': button_power_click_start_cb,
    'click_release': button_power_click_release_cb,
    'long_click_start': button_power_long_click_start_cb,
    'long_click_release': button_power_long_click_release_cb
  },
  button_LIGHTS: {
    'switch_change': button_lights_switch_change_cb
  },
}

def _positive_cfg_int(name, default):
  try:
    value = int(getattr(cfg, name, default))
  except Exception:
    return default
  return value if value > 0 else default

button_debounce_ms = _positive_cfg_int("debounce_ms", 50)
button_click_min_ms = _positive_cfg_int("power_btn_click_min_ms", 100)
power_button_long_ms = _positive_cfg_int("power_btn_long_ms", 1000)

vars.buttons = [None]*nr_buttons
for i, pin in enumerate(BUTTON_PINS):
  btn = thisButton(pin, True)
  btn.setDebounceThreshold(button_debounce_ms)
  btn.setClickMinThreshold(button_click_min_ms)
  btn.setLongPressThreshold(power_button_long_ms)
  if 'switch_change' in buttons_callbacks[i]:
    btn.setSwitchMode(True)
    btn.assignSwitchChange(buttons_callbacks[i]['switch_change'])
  if 'click_start' in buttons_callbacks[i]:
    btn.assignClickStart(buttons_callbacks[i]['click_start'])
  if 'click_release' in buttons_callbacks[i]:
    btn.assignClickRelease(buttons_callbacks[i]['click_release'])
  if 'long_click_start' in buttons_callbacks[i]:
    btn.assignLongClickStart(buttons_callbacks[i]['long_click_start'])
  if 'long_click_release' in buttons_callbacks[i]:
    btn.assignLongClickRelease(buttons_callbacks[i]['long_click_release'])
  vars.buttons[i] = btn
boot_log("Buttons initialized")

async def power_off_forever(backlight_timeout_ms):
  """
  Block forever: keep OFF states latched and only poll POWER to allow a hard reset.
  Any change on POWER bit (0x0100) triggers machine.reset().
  """
  buttons_state_previous = bool(vars.buttons_state & 0x0100)
  backlight_idle_since = time.ticks_ms()
  period_ms = 100
  next_wake = time.ticks_ms()
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
      power_button_is_active() or
      vars.motor_current_x10 > 10 or
      vars.wheel_speed_x10 != 0 or
      vars.throttle_is_active
    )

    if wake_backlight:
      backlight_idle_since = now
      set_backlight_enabled(True)
    elif time.ticks_diff(now, backlight_idle_since) >= backlight_timeout_ms:
      set_backlight_enabled(False)

    try:
      motor_board.send_data()
      lights_board.send_data()
      power_ok = _send_power_packet(" ".join((
        str(int(MSG_COMMAND)),
        str(int(BOARD_DISPLAY)),
        str(int(BOARD_POWER_SWITCH)),
        str(int(POWER_SWITCH_CMD)),
        str(int(vars.turn_off_relay)),
      )).encode("ascii"))
      vars.power_switch_board_comm_ok = bool(power_ok)
    except Exception as ex:
      print("send_off_once err:", ex)
      vars.power_switch_board_comm_ok = False

    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    await asyncio.sleep_ms(remaining if remaining > 0 else 0)

async def ui_task(fb, lcd, vars):
  global screen_manager
  
  # Main screen takes about 80ms to update
  period_ms = 100
  next_wake = time.ticks_ms()
  
  while True:
    screen_manager.update(vars)
    screen_manager.render(vars)
  
    # Control loop time
    next_wake = time.ticks_add(next_wake, period_ms)
    remaining = time.ticks_diff(next_wake, time.ticks_ms())
    if remaining > 0:
      await asyncio.sleep_ms(remaining)
    else:
      await asyncio.sleep_ms(0)

async def rtc_sync_task(vars, delay_ms=2000):
  bms_should_resume = False
  await asyncio.sleep_ms(delay_ms)
  vars.rtc_sync_pending = False
  # The sync belongs to the charging session that scheduled it.  If the
  # rider left before the delay expired, leave the session available to retry.
  if not screen_manager.current_is(ScreenID.CHARGING):
    vars.rtc_sync_result = 'idle'
    vars.rtc_sync_done_for_charging_session = False
    return
  vars.rtc_sync_started = True
  vars.rtc_sync_result = 'pending'
  vars.charging_reconfirm_failed = False
  # Keep the charging screen latched until fresh BMS data confirms whether
  # charging continued during the Wi-Fi/BLE radio handover. A configuration
  # without a BMS has no evidence source to wait for.
  vars.charging_reconfirm_pending = bool(cfg.has_jbd_bms)
  # Do not start the timeout while Wi-Fi is still searching for the router.
  # It starts below once ESP-NOW is rebuilt and BLE has been restarted.
  vars.charging_reconfirm_started_ms = 0
  # Do not carry a charging decision across the Wi-Fi/BLE radio handover.
  # Charging must be re-confirmed after the BMS reconnects with fresh data.
  vars.battery_is_charging = False
  vars.bms_battery_current_x100 = None
  vars.comms_paused = True
  try:
    if bms is not None:
      # A temporarily unavailable client still owns BLE state. Stop and
      # restart every started client so post-sync charging always depends on
      # a new BMS BASIC frame, never on the pre-sync connection state.
      bms_should_resume = bms.is_started()
      if bms_should_resume:
        bms.stop(deactivate=True)
    # Release the ESP-NOW radio/channel before scanning for the WiFi router.
    # The ESP-NOW stack is rebuilt on channel 1 after the sync completes.
    _esp.active(False)
    previous_rtc_ntp_sync_valid = bool(vars.rtc_ntp_sync_valid)
    rtc_ntp_sync_valid, rtc_time_valid, rtc_sync_error = await sync_rtc_time_from_wifi_ntp_async_lazy(
      vars.rtc,
      wifi_timeout_s=cfg.rtc_wifi_timeout_s,
      ntp_timeout_s=cfg.rtc_ntp_timeout_s,
    )
    vars.rtc_ntp_sync_valid = bool(rtc_ntp_sync_valid)
    if vars.rtc.has_external_rtc() and previous_rtc_ntp_sync_valid:
      vars.rtc_ntp_sync_valid = True
    vars.rtc_time_valid = bool(rtc_time_valid)
    if rtc_sync_error is not None:
      vars.rtc_sync_result = rtc_sync_error
    elif rtc_ntp_sync_valid:
      vars.rtc_sync_result = 'success'
    else:
      vars.rtc_sync_result = 'idle'
    if vars.rtc.has_external_rtc():
      save_rtc_ntp_sync_valid(vars.rtc_ntp_sync_valid)
    update_time_string(vars)
    if vars.rtc_ntp_sync_valid:
      update_auto_lights_state(vars)
  except Exception as ex:
    vars.rtc_sync_result = 'general_fail'
    print(ex)
  finally:
    await asyncio.sleep_ms(300)
    try:
      _rebuild_espnow_stack()
    except Exception as ex:
      if ESPNOW_DEBUG:
        print("ESP-NOW rebuild failed:", ex)
      vars.comms_paused = False
      machine.reset()
    else:
      if bms_should_resume:
        try:
          bms.start(scan_ms=8000)
        except Exception as ex:
          if getattr(cfg, "bms_debug", False):
            print("BMS restart failed:", ex)
      # Keep the CHARGING latch over the whole radio handover. The timeout
      # starts only once a fresh BLE scan can actually begin, so a missing
      # Wi-Fi router cannot consume the BMS reconfirmation window.
      if vars.charging_reconfirm_pending:
        vars.charging_reconfirm_started_ms = time.ticks_ms()
      vars.comms_paused = False
    # Allow a fresh sync when the next charging session starts.  The charging
    # screen remains latched separately until fresh BMS data is evaluated.
    vars.rtc_sync_started = False


async def preload_screens_task(delay_ms=0):
  await asyncio.sleep_ms(delay_ms)
  boot_log("Preload screens start")
  for screen_id, label in (
    (ScreenID.MAIN, "MAIN"),
    (ScreenID.CHARGING, "CHARGING"),
    (ScreenID.BATTERY_RESISTANCE, "BATTERY_RESISTANCE"),
    (ScreenID.POWEROFF, "POWEROFF"),
    (ScreenID.MOTOR_BLOCKED, "MOTOR_BLOCKED"),
  ):
    try:
      preload_start_ms = time.ticks_ms()
      screen_manager.preload(screen_id)
      if cfg.boot_timing_debug:
        print("[boot preload +{:>4} ms] {} ready".format(
          time.ticks_diff(time.ticks_ms(), preload_start_ms), label))
    except Exception as ex:
      print("{} preload failed:".format(label.title()), ex)
    # Yield without adding fixed startup latency.
    await asyncio.sleep_ms(0)
  boot_log("Preload screens complete")

async def main_task(vars):
  global screen_manager
  
  motor_power_previous = 0
  charge_seen_ms = None
  non_charging_seen_ms = None
  stationary_since_ms = None
  was_in_charging_screen = screen_manager.current_is(ScreenID.CHARGING)
  was_comms_paused = vars.comms_paused
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

    if (
      vars.charging_reconfirm_pending and
      vars.charging_reconfirm_started_ms and
      time.ticks_diff(now, vars.charging_reconfirm_started_ms) >=
          CHARGING_RECONFIRM_TIMEOUT_MS
    ):
      # Keep the rider-facing state explicit instead of silently reporting
      # non-charging without fresh evidence. The rider can acknowledge this
      # state with a power long-press.
      vars.charging_reconfirm_pending = False
      vars.charging_reconfirm_started_ms = 0
      vars.charging_reconfirm_failed = True

    if was_comms_paused and not vars.comms_paused:
      # Force a new charging hold interval after Wi-Fi/NTP radio recovery.
      charge_seen_ms = None
      non_charging_seen_ms = None
      stationary_since_ms = None
      vars.battery_is_charging = False
      vars.bms_battery_current_x100 = None
      vars.bms_battery_current_last_update_ms = 0
    was_comms_paused = vars.comms_paused

    # Charging is valid only while motor-board telemetry is fresh.  In
    # particular, regen can leave a positive BMS current sample behind when
    # the wheel reaches zero; accept it only if it was sampled after a stable,
    # non-braking standstill.
    if cfg.has_jbd_bms and not vars.rtc_sync_pending and not vars.comms_paused:
      vehicle_is_stationary = (
        vars.motor_board_rx_ok and
        vars.rear_speed_telemetry_valid and
        vars.wheel_speed_x10 == 0 and
        not vars.brakes_are_active and
        not vars.regen_braking_is_active
      )
      if not vehicle_is_stationary:
        vars.battery_is_charging = False
        charge_seen_ms = None
        non_charging_seen_ms = None
        stationary_since_ms = None
      elif stationary_since_ms is None:
        stationary_since_ms = now
      elif vars.bms_battery_current_x100 is not None:
        bms_current_is_post_stop = time.ticks_diff(
          vars.bms_battery_current_last_update_ms, stationary_since_ms
        ) >= 0
        if (
          bms_current_is_post_stop and
          vars.bms_battery_current_x100 > cfg.charge_current_threshold_a_x100
        ):
          non_charging_seen_ms = None
          if charge_seen_ms is None:
            charge_seen_ms = now
          elif time.ticks_diff(now, charge_seen_ms) >= cfg.charge_detect_hold_ms:
            vars.battery_is_charging = True
            vars.charging_reconfirm_pending = False
            vars.charging_reconfirm_started_ms = 0
            vars.charging_reconfirm_failed = False
        else:
          charge_seen_ms = None
          # A single fresh non-charging sample is not sufficient to end the
          # session. This is especially important immediately after BLE has
          # been restarted for NTP sync: the first BASIC frame can be stale or
          # incomplete while the BMS connection settles.
          if bms_current_is_post_stop:
            if vars.battery_is_charging or vars.charging_reconfirm_pending:
              if non_charging_seen_ms is None:
                non_charging_seen_ms = now
              elif time.ticks_diff(
                now, non_charging_seen_ms
              ) >= cfg.charge_detect_hold_ms:
                vars.battery_is_charging = False
                vars.charging_reconfirm_pending = False
                vars.charging_reconfirm_started_ms = 0
                vars.charging_reconfirm_failed = False
                # A sustained fresh BMS reading proves this session ended;
                # permit a sync for the next real charging session.
                vars.rtc_sync_done_for_charging_session = False
            else:
              vars.battery_is_charging = False
      elif bms is None or not bms.is_available():
        charge_seen_ms = None
        non_charging_seen_ms = None
        stationary_since_ms = None
        # During post-sync reconfirmation, absence of a BMS frame is unknown,
        # not proof that charging stopped. Keep the screen latch until fresh
        # evidence arrives or its explicit timeout handles it.
        if not vars.charging_reconfirm_pending:
          vars.battery_is_charging = False
    elif vars.charging_reconfirm_pending:
      # No BMS-backed charging detector is active for this configuration.
      vars.charging_reconfirm_pending = False
      vars.charging_reconfirm_started_ms = 0

    in_main_screen = screen_manager.current_is(ScreenID.MAIN)
    in_charging_screen = screen_manager.current_is(ScreenID.CHARGING)

    if was_in_charging_screen and not in_charging_screen:
      if vars.rtc_sync_result in (
        'ssid_missing', 'password_wrong', 'general_fail'
      ):
        vars.rtc_sync_result = 'idle'

    if (
      cfg.enable_rtc_time and
      in_charging_screen and
      not was_in_charging_screen and
      not vars.rtc_sync_pending and
      not vars.rtc_sync_done_for_charging_session
    ):
      vars.rtc_sync_pending = True
      vars.rtc_sync_done_for_charging_session = True
      vars.rtc_sync_result = 'pending'
      asyncio.create_task(rtc_sync_task(vars, delay_ms=RTC_SYNC_DELAY_MS))
    was_in_charging_screen = in_charging_screen
    
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
      power_button_is_active() or
      vars.motor_current_x10 > 10 or
      vars.wheel_speed_x10 != 0 or
      vars.throttle_is_active
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
      if not save_battery_resistance_history(
          vars, battery_resistance_config):
        print("Battery resistance history save failed")
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

async def motor_comms_task(vars):
  global _last_power_config_sent, _last_power_switch_sent
  global _last_power_config_feedback
  global _last_power_switch_tx_attempt_ms, _last_power_switch_tx_ok_ms
  global _next_power_switch_tx_ms
  period_ms = 50
  next_wake = time.ticks_ms()
  next_motor_command_ms = next_wake
  next_lights_command_ms = next_wake
  next_motor_status_receive_ms = next_wake
  last_lights_command = None
  lights_retry_ms = LIGHTS_RETRY_MS
  while True:
    now = time.ticks_ms()

    if vars.comms_paused:
      await asyncio.sleep_ms(50)
      continue

    if time.ticks_diff(now, next_motor_command_ms) >= 0:
      motor_ok = motor_board.send_data()
      next_motor_command_ms = time.ticks_add(
        now, espnow_jittered_period_ms(100)
      )
    else:
      motor_ok = False
    current_lights_command = _display_lights_state()
    if (
      current_lights_command != last_lights_command or
      time.ticks_diff(now, next_lights_command_ms) >= 0
    ):
      lights_ok = lights_board.send_data()
      last_lights_command = current_lights_command
      if lights_ok:
        lights_retry_ms = LIGHTS_RETRY_MS
      else:
        lights_retry_ms = min(LIGHTS_RETRY_MAX_MS, lights_retry_ms * 2)
      next_lights_command_ms = time.ticks_add(
        now,
        espnow_jittered_period_ms(
          LIGHTS_HEARTBEAT_MS if lights_ok else lights_retry_ms
        ),
      )
    else:
      lights_ok = None
    current_power_switch = bool(vars.turn_off_relay)
    power_switch_ok = time.ticks_diff(now, _last_power_switch_tx_ok_ms) < POWER_SWITCH_BOARD_COMM_TIMEOUT_MS
    if (
      current_power_switch != _last_power_switch_sent or
      time.ticks_diff(now, _next_power_switch_tx_ms) >= 0
    ):
      power_switch_ok = _send_power_packet(" ".join((
        str(int(MSG_COMMAND)),
        str(int(BOARD_DISPLAY)),
        str(int(BOARD_POWER_SWITCH)),
        str(int(POWER_SWITCH_CMD)),
        str(int(vars.turn_off_relay)),
      )).encode("ascii"))
      _last_power_switch_tx_attempt_ms = now
      _next_power_switch_tx_ms = time.ticks_add(
        now, espnow_jittered_period_ms(POWER_SWITCH_HEARTBEAT_MS)
      )
      if power_switch_ok:
        _last_power_switch_tx_ok_ms = now
      _last_power_switch_sent = current_power_switch
    current_power_config = _power_config_snapshot()
    _send_power_config_if_needed(now, current_power_config)

    if motor_ok:
      vars.motor_board_tx_last_ok_ms = now
    vars.motor_board_tx_ok = time.ticks_diff(now, vars.motor_board_tx_last_ok_ms) < MOTOR_BOARD_TX_COMM_TIMEOUT_MS
    if lights_ok:
      vars.lights_board_tx_last_ok_ms = now
    vars.lights_board_comm_ok = time.ticks_diff(
      now, vars.lights_board_tx_last_ok_ms
    ) < LIGHTS_BOARD_TX_COMM_TIMEOUT_MS
    vars.power_switch_board_comm_ok = bool(power_switch_ok)

    if time.ticks_diff(now, next_motor_status_receive_ms) >= 0:
      next_motor_status_receive_ms = time.ticks_add(now, 250)
      latest_motor_status = None
      for host, packet in espnow_recv_all(_esp, debug=ESPNOW_DEBUG):
        if packet is None:
          continue

        parts = parse_frame(packet)
        if parts is None:
          continue

        if len(parts) >= 14 and parts[0] == MSG_STATUS and parts[1] == BOARD_MOTOR and parts[2] == BOARD_DISPLAY:
          latest_motor_status = parts
          continue

        power_status = decode_power_switch_status(packet)
        if power_status is not None:
          vars.power_switch_board_comm_ok = True
          received_config = tuple(int(value) for value in power_status[4:9])
          if received_config != _last_power_config_feedback:
            expected_config = _last_power_config_sent
            if expected_config is None:
              print("Power board config feedback:", received_config, "expected: none")
            elif received_config == expected_config:
              print("Power board config applied:", received_config)
            else:
              print("Power board config mismatch; rx:", received_config, "tx:", expected_config)
            _last_power_config_feedback = received_config

      if latest_motor_status is not None:
        parts = latest_motor_status
        vars.motor_board_rx_last_ok_ms = now
        health_bitmap = parts[3]
        vars.motor_lights_tx_ok = bool(health_bitmap & HEALTH_MOTOR_LIGHTS_TX_OK)
        vars.rear_speed_telemetry_valid = bool(
          health_bitmap & HEALTH_MOTOR_REAR_SPEED_VALID)

        vars.battery_voltage_x10 = parts[4]
        vars.battery_current_x10 = parts[5]
        vars.battery_soc_x1000 = parts[6]
        vars.motor_current_x10 = parts[7]
        vars.wheel_speed_x10 = parts[8]
        flags = parts[9]
        vars.brakes_are_active = bool(flags & (1 << 0))
        vars.regen_braking_is_active = bool(flags & (1 << 1))
        vars.motor_throttle_rearm_required = bool(flags & (1 << 2))
        vars.mode = (flags >> 3) & 0x07
        vars.cruise_control_is_active = bool(flags & (1 << 6))
        vars.throttle_is_active = bool(flags & (1 << 7))
        vars.throttle_right_fault = bool(flags & (1 << 8))
        vars.throttle_left_fault = bool(flags & (1 << 9))
        vars.rear_vesc_temperature_x10 = parts[10]
        vars.front_vesc_temperature_x10 = parts[11]
        vars.rear_motor_temperature_x10 = parts[12]
        vars.front_motor_temperature_x10 = parts[13]

        if len(parts) >= 15 and \
            vars.battery_resistance_enabled and \
            vars.battery_resistance_measurement_available and \
            not vars.battery_resistance_received_this_boot:
          resistance_mohm = parts[14]
          if (battery_resistance_config.min_mohm <= resistance_mohm <=
              battery_resistance_config.max_mohm):
            vars.battery_resistance_received_this_boot = True
            record_battery_resistance_result(vars, resistance_mohm)

        # Newer motor boards append the estimator diagnostic snapshot.
        if len(parts) >= 20:
          vars.battery_resistance_debug_phase = parts[15]
          vars.battery_resistance_debug_boot_seconds = parts[16]
          vars.battery_resistance_debug_error_count = parts[17]
          vars.battery_resistance_debug_sample_count = parts[18]
          vars.battery_resistance_debug_reference_sample_count = parts[19]
          if len(parts) >= 21:
            vars.battery_resistance_debug_phase_elapsed_seconds = parts[20]
          if len(parts) >= 23:
            vars.lisp_motion_loss_count = parts[21]
            vars.lisp_thermal_loss_count = parts[22]

    vars.motor_board_rx_ok = time.ticks_diff(now, vars.motor_board_rx_last_ok_ms) < MOTOR_BOARD_RX_COMM_TIMEOUT_MS
    if not vars.motor_board_rx_ok:
      vars.motor_lights_tx_ok = False
      vars.rear_speed_telemetry_valid = False

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
    tasks = []
    tasks.append(asyncio.create_task(ui_task(fb, lcd, vars)))
    await asyncio.sleep_ms(0)
    tasks.append(asyncio.create_task(preload_screens_task()))
    tasks.append(asyncio.create_task(motor_comms_task(vars)))
    tasks.append(asyncio.create_task(main_task(vars)))
    if bms is not None:
      tasks.append(asyncio.create_task(bms_task(bms, vars)))
      tasks.append(asyncio.create_task(bms_read_task(bms, vars)))
    boot_log("Main tasks started")

    await asyncio.gather(*tasks)
    
  finally:
    pass

asyncio.run(main())
