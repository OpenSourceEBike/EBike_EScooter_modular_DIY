import time
import network
import ntptime

try:
  import socket
except ImportError:
  try:
    import usocket as socket
  except ImportError:
    socket = None


def _wifi_status_name(status):
  names = {
    1000: "STAT_IDLE",
    1001: "STAT_CONNECTING",
    1010: "STAT_GOT_IP",
    200: "STAT_BEACON_TIMEOUT",
    201: "STAT_NO_AP_FOUND",
    202: "STAT_WRONG_PASSWORD",
    203: "STAT_ASSOC_FAIL",
    204: "STAT_HANDSHAKE_TIMEOUT",
  }
  return names.get(status, str(status))


def _log_wifi_scan(sta, target_ssid):
  try:
    scan_results = sta.scan()
    matches = []
    for entry in scan_results:
      try:
        ssid = entry[0].decode("utf-8")
      except Exception:
        ssid = str(entry[0])
      if ssid == target_ssid:
        matches.append(entry)

    if not matches:
      print("WiFi scan: target SSID not found:", target_ssid)
      return

    for entry in matches:
      ssid, bssid, channel, rssi, authmode, hidden = entry[:6]
      try:
        ssid = ssid.decode("utf-8")
      except Exception:
        ssid = str(ssid)
      print(
        "WiFi scan match: ssid={} channel={} rssi={} authmode={} hidden={}".format(
          ssid, channel, rssi, authmode, hidden
        )
      )
  except Exception as e:
    print("WiFi scan failed:", e)


def _set_socket_timeout(timeout_s):
  if socket is None:
    return None

  setter = getattr(socket, "setdefaulttimeout", None)
  getter = getattr(socket, "getdefaulttimeout", None)
  if setter is None:
    return None

  previous = None
  if getter is not None:
    try:
      previous = getter()
    except Exception:
      previous = None

  try:
    setter(timeout_s)
  except Exception:
    return None

  return previous


def _restore_socket_timeout(previous):
  if socket is None:
    return

  setter = getattr(socket, "setdefaulttimeout", None)
  if setter is None:
    return

  try:
    setter(previous)
  except Exception:
    pass


def _load_wifi_credentials(ssid, password):
  if ssid is not None and password is not None:
    return ssid, password

  import secrets
  return (
    ssid or secrets.secrets["wifi_ssid"],
    password or secrets.secrets["wifi_password"],
  )


def _connect_wifi(sta, ssid, password, timeout_s=15):
  sta.active(True)
  _log_wifi_scan(sta, ssid)
  if sta.isconnected():
    return sta

  sta.connect(ssid, password)
  t0 = time.ticks_ms()
  last_status = None
  while not sta.isconnected():
    status = sta.status()
    if status != last_status:
      print("WiFi status:", _wifi_status_name(status))
      last_status = status
    if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
      print("WiFi final status:", _wifi_status_name(sta.status()))
      raise OSError("WiFi connect timeout")
    time.sleep_ms(200)
  return sta


async def _connect_wifi_async(sta, ssid, password, timeout_s=5):
  import uasyncio as asyncio

  sta.active(True)
  _log_wifi_scan(sta, ssid)
  if sta.isconnected():
    return sta

  sta.connect(ssid, password)
  t0 = time.ticks_ms()
  last_status = None
  while not sta.isconnected():
    status = sta.status()
    if status != last_status:
      print("WiFi status:", _wifi_status_name(status))
      last_status = status
    if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
      print("WiFi final status:", _wifi_status_name(sta.status()))
      raise OSError("WiFi connect timeout")
    await asyncio.sleep_ms(200)
  return sta


def _reset_wifi_radio():
  sta = network.WLAN(network.STA_IF)
  sta.active(False)
  time.sleep_ms(200)
  sta.active(True)


async def _reset_wifi_radio_async():
  import uasyncio as asyncio

  sta = network.WLAN(network.STA_IF)
  sta.active(False)
  await asyncio.sleep_ms(200)
  sta.active(True)


def sync_rtc_time_from_wifi_ntp(
  rtc,
  ssid=None,
  password=None,
  ntp_host="pool.ntp.org",
  wifi_timeout_s=15,
  ntp_timeout_s=3,
):
  try:
    ssid, password = _load_wifi_credentials(ssid, password)
  except Exception:
    print("Missing or invalid secrets.py!")
    return rtc.update_internal_rtc_from_external()

  previous_socket_timeout = None
  try:
    sta = network.WLAN(network.STA_IF)
    _connect_wifi(sta, ssid, password, timeout_s=wifi_timeout_s)
    print("Connected to WiFi:", ssid)

    previous_socket_timeout = _set_socket_timeout(ntp_timeout_s)
    ntptime.host = ntp_host
    ntptime.settime()  # internal RTC now in UTC

    utc_now = rtc.internal_utc_now()
    now, offset_s = rtc.localtime_from_utc(utc_now)
    offset_h = offset_s // 3600
    print(
      "Local RTC time (UTC%+d): %02d:%02d:%02d" % (
        offset_h, now[3], now[4], now[5]
      )
    )
    print("RTC internal kept in UTC:", utc_now)

    if rtc.has_external_rtc():
      rtc.set_external_utc(utc_now)
      print("RTC external updated to UTC:", rtc.external_utc_now())

    _reset_wifi_radio()
    return True

  except Exception as e:
    if str(e) == "WiFi connect timeout":
      print("Failed to connect to WiFi:", e)
    else:
      print("Error fetching time from NTP:", e)
    try:
      _reset_wifi_radio()
    except Exception as reset_ex:
      print("Radio reset failed:", reset_ex)
    return rtc.update_internal_rtc_from_external()

  finally:
    _restore_socket_timeout(previous_socket_timeout)


async def sync_rtc_time_from_wifi_ntp_async(
  rtc,
  ssid=None,
  password=None,
  ntp_host="pool.ntp.org",
  wifi_timeout_s=5,
  ntp_timeout_s=3,
):
  try:
    ssid, password = _load_wifi_credentials(ssid, password)
  except Exception:
    print("Missing or invalid secrets.py!")
    return rtc.update_internal_rtc_from_external()

  previous_socket_timeout = None
  try:
    sta = network.WLAN(network.STA_IF)
    await _connect_wifi_async(sta, ssid, password, timeout_s=wifi_timeout_s)
    print("Connected to WiFi:", ssid)

    previous_socket_timeout = _set_socket_timeout(ntp_timeout_s)
    ntptime.host = ntp_host
    ntptime.settime()  # internal RTC now in UTC

    utc_now = rtc.internal_utc_now()
    now, offset_s = rtc.localtime_from_utc(utc_now)
    offset_h = offset_s // 3600
    print(
      "Local RTC time (UTC%+d): %02d:%02d:%02d" % (
        offset_h, now[3], now[4], now[5]
      )
    )
    print("RTC internal kept in UTC:", utc_now)

    if rtc.has_external_rtc():
      rtc.set_external_utc(utc_now)
      print("RTC external updated to UTC:", rtc.external_utc_now())

    await _reset_wifi_radio_async()
    return True

  except Exception as e:
    if str(e) == "WiFi connect timeout":
      print("Failed to connect to WiFi:", e)
    else:
      print("Error fetching time from NTP:", e)
    try:
      await _reset_wifi_radio_async()
    except Exception as reset_ex:
      print("Radio reset failed:", reset_ex)
    return rtc.update_internal_rtc_from_external()

  finally:
    _restore_socket_timeout(previous_socket_timeout)
