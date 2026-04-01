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
  return _connect_wifi_common(sta, ssid, password, timeout_s=timeout_s)


async def _connect_wifi_async(sta, ssid, password, timeout_s=5):
  import uasyncio as asyncio

  return await _connect_wifi_common_async(sta, ssid, password, timeout_s=timeout_s)


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


def _disconnect_wifi(sta):
  try:
    sta.disconnect()
  except Exception:
    pass


def _prepare_wifi_station(sta):
  try:
    ap = network.WLAN(network.AP_IF)
    if ap.active():
      ap.active(False)
  except Exception:
    pass

  if sta.active():
    _disconnect_wifi(sta)
  else:
    sta.active(True)


def _connect_wifi_attempt(sta, ssid, password, timeout_s):
  _prepare_wifi_station(sta)
  _log_wifi_scan(sta, ssid)

  if sta.isconnected():
    return sta

  sta.connect(ssid, password)
  t0 = time.ticks_ms()
  last_status = None
  terminal_statuses = {200, 201, 202, 203, 204}

  while not sta.isconnected():
    status = sta.status()
    if status != last_status:
      print("WiFi status:", _wifi_status_name(status))
      last_status = status
    if status in terminal_statuses:
      raise OSError("WiFi connect failed: {}".format(_wifi_status_name(status)))
    if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
      print("WiFi final status:", _wifi_status_name(sta.status()))
      raise OSError("WiFi connect timeout")
    time.sleep_ms(200)

  return sta


async def _connect_wifi_attempt_async(sta, ssid, password, timeout_s):
  import uasyncio as asyncio

  _prepare_wifi_station(sta)
  _log_wifi_scan(sta, ssid)

  if sta.isconnected():
    return sta

  sta.connect(ssid, password)
  t0 = time.ticks_ms()
  last_status = None
  terminal_statuses = {200, 201, 202, 203, 204}

  while not sta.isconnected():
    status = sta.status()
    if status != last_status:
      print("WiFi status:", _wifi_status_name(status))
      last_status = status
    if status in terminal_statuses:
      raise OSError("WiFi connect failed: {}".format(_wifi_status_name(status)))
    if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
      print("WiFi final status:", _wifi_status_name(sta.status()))
      raise OSError("WiFi connect timeout")
    await asyncio.sleep_ms(200)

  return sta


def _connect_wifi_common(sta, ssid, password, timeout_s=15):
  try:
    return _connect_wifi_attempt(sta, ssid, password, timeout_s)
  except Exception as first_error:
    print("WiFi first attempt failed:", first_error)
    _reset_wifi_radio()
    retry_sta = network.WLAN(network.STA_IF)
    retry_timeout_s = max(timeout_s, 15)
    print("Retrying WiFi connect with timeout_s =", retry_timeout_s)
    return _connect_wifi_attempt(retry_sta, ssid, password, retry_timeout_s)


async def _connect_wifi_common_async(sta, ssid, password, timeout_s=5):
  try:
    return await _connect_wifi_attempt_async(sta, ssid, password, timeout_s)
  except Exception as first_error:
    print("WiFi first attempt failed:", first_error)
    await _reset_wifi_radio_async()
    retry_sta = network.WLAN(network.STA_IF)
    retry_timeout_s = max(timeout_s, 15)
    print("Retrying WiFi connect with timeout_s =", retry_timeout_s)
    return await _connect_wifi_attempt_async(retry_sta, ssid, password, retry_timeout_s)


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
      "Displayed local time (UTC%+d): %02d:%02d:%02d" % (
        offset_h, now[3], now[4], now[5]
      )
    )
    print("RTC stored internally in UTC:", utc_now)

    if rtc.has_external_rtc():
      rtc.set_external_utc(utc_now)
      print("External RTC stored in UTC:", rtc.external_utc_now())

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
      "Displayed local time (UTC%+d): %02d:%02d:%02d" % (
        offset_h, now[3], now[4], now[5]
      )
    )
    print("RTC stored internally in UTC:", utc_now)

    if rtc.has_external_rtc():
      rtc.set_external_utc(utc_now)
      print("External RTC stored in UTC:", rtc.external_utc_now())

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
