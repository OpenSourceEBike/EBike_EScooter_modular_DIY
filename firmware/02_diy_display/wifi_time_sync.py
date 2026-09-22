import time
import network
import ntptime
import struct

try:
  import socket
except ImportError:
  try:
    import usocket as socket
  except ImportError:
    socket = None


NTP_PORT = 123
DNS_PORT = 53
NTP_PACKET_SIZE = 48
NTP_TO_2000_EPOCH_SECONDS = 3155673600


def _ipv4_literal(value):
  try:
    parts = value.split('.')
    if len(parts) != 4:
      return None
    numbers = [int(part) for part in parts]
    if any(number < 0 or number > 255 for number in numbers):
      return None
    return '.'.join(str(number) for number in numbers)
  except (AttributeError, TypeError, ValueError):
    return None


def _build_dns_query(host, transaction_id):
  labels = host.split('.')
  query = bytearray(12)
  query[0] = (transaction_id >> 8) & 0xFF
  query[1] = transaction_id & 0xFF
  query[2] = 0x01  # recursion desired
  query[5] = 0x01  # one question
  for label in labels:
    encoded = label.encode('ascii')
    if not encoded or len(encoded) > 63:
      raise ValueError('invalid DNS host')
    query.append(len(encoded))
    query.extend(encoded)
  query.extend(b'\x00\x00\x01\x00\x01')  # root, A, IN
  return bytes(query)


def _skip_dns_name(packet, offset):
  packet_len = len(packet)
  while offset < packet_len:
    length = packet[offset]
    if length == 0:
      return offset + 1
    if length & 0xC0 == 0xC0:
      if offset + 1 >= packet_len:
        return None
      return offset + 2
    if length & 0xC0:
      return None
    offset += 1 + length
  return None


def _parse_dns_ipv4_response(packet, transaction_id):
  if len(packet) < 12:
    return None
  received_id = (packet[0] << 8) | packet[1]
  flags = (packet[2] << 8) | packet[3]
  if (received_id != transaction_id or not (flags & 0x8000) or
      (flags & 0x000F)):
    return None
  question_count = (packet[4] << 8) | packet[5]
  answer_count = (packet[6] << 8) | packet[7]
  offset = 12
  for _ in range(question_count):
    offset = _skip_dns_name(packet, offset)
    if offset is None or offset + 4 > len(packet):
      return None
    offset += 4
  for _ in range(answer_count):
    offset = _skip_dns_name(packet, offset)
    if offset is None or offset + 10 > len(packet):
      return None
    record_type = (packet[offset] << 8) | packet[offset + 1]
    record_class = (packet[offset + 2] << 8) | packet[offset + 3]
    data_length = (packet[offset + 8] << 8) | packet[offset + 9]
    offset += 10
    if offset + data_length > len(packet):
      return None
    if record_type == 1 and record_class == 1 and data_length == 4:
      return '.'.join(str(value) for value in packet[offset:offset + 4])
    offset += data_length
  return None


def _ntp_seconds_to_utc(ntp_seconds):
  # MicroPython ports use either 1970 or 2000 as the epoch. Derive the NTP
  # offset from the port's own mktime result instead of assuming one.
  try:
    seconds_at_2000 = int(time.mktime((2000, 1, 1, 0, 0, 0, 0, 0)))
  except TypeError:
    # CPython host tests require the DST field; MicroPython uses 8-tuples.
    seconds_at_2000 = int(time.mktime((2000, 1, 1, 0, 0, 0, 0, 1, -1)))
  ntp_delta = NTP_TO_2000_EPOCH_SECONDS - seconds_at_2000
  return time.gmtime(int(ntp_seconds) - ntp_delta)


async def _udp_exchange_async(payload, address, deadline_ms, response_size):
  if socket is None:
    raise OSError('socket module unavailable')
  import uasyncio as asyncio

  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    try:
      sock.setblocking(False)
    except AttributeError:
      sock.settimeout(0)

    sent = False
    while not sent:
      try:
        sock.sendto(payload, address)
        sent = True
      except OSError:
        if time.ticks_diff(deadline_ms, time.ticks_ms()) <= 0:
          raise OSError('UDP send timeout')
        await asyncio.sleep_ms(20)

    while True:
      try:
        data, _source = sock.recvfrom(response_size)
        if data:
          return data
      except OSError:
        pass
      if time.ticks_diff(deadline_ms, time.ticks_ms()) <= 0:
        raise OSError('UDP receive timeout')
      await asyncio.sleep_ms(20)
  finally:
    try:
      sock.close()
    except Exception:
      pass


async def _resolve_ipv4_async(sta, host, deadline_ms):
  literal = _ipv4_literal(host)
  if literal is not None:
    return literal
  try:
    dns_server = sta.ifconfig()[3]
  except Exception:
    raise OSError('DNS server unavailable')
  if _ipv4_literal(dns_server) is None:
    raise OSError('invalid DNS server')
  transaction_id = time.ticks_ms() & 0xFFFF
  response = await _udp_exchange_async(
    _build_dns_query(host, transaction_id),
    (dns_server, DNS_PORT),
    deadline_ms,
    512,
  )
  resolved = _parse_dns_ipv4_response(response, transaction_id)
  if resolved is None:
    raise OSError('DNS response invalid')
  return resolved


async def _set_rtc_from_ntp_async(rtc, sta, ntp_host, timeout_s):
  timeout_ms = max(1, int(timeout_s * 1000))
  deadline_ms = time.ticks_add(time.ticks_ms(), timeout_ms)
  ntp_ip = await _resolve_ipv4_async(sta, ntp_host, deadline_ms)
  request = bytearray(NTP_PACKET_SIZE)
  request[0] = 0x1B  # client, NTP version 3
  response = await _udp_exchange_async(
    request,
    (ntp_ip, NTP_PORT),
    deadline_ms,
    NTP_PACKET_SIZE,
  )
  if len(response) < NTP_PACKET_SIZE:
    raise OSError('short NTP response')
  mode = response[0] & 0x07
  stratum = response[1]
  if mode not in (4, 5) or stratum == 0:
    raise OSError('invalid NTP response')
  ntp_seconds = struct.unpack('>I', response[40:44])[0]
  utc_now = _ntp_seconds_to_utc(ntp_seconds)
  rtc.set_internal_utc(utc_now)
  return rtc.internal_utc_now()


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
      return None

    selected = None
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
      if selected is None or rssi > selected[2]:
        selected = (bssid, channel, rssi)
    return selected
  except Exception as e:
    print("WiFi scan failed:", e)
    return None


def _configure_wifi_target(sta, scan_target):
  if scan_target is None:
    return

  bssid, channel, _rssi = scan_target
  print("WiFi target channel from scan:", channel)
  print("WiFi target BSSID from scan:", bssid)

  # BSSID pinning is optional because some MicroPython ports do not expose
  # this station configuration key.
  try:
    sta.config(bssid=bssid)
    print("WiFi target BSSID applied:", bssid)
  except (AttributeError, OSError, ValueError):
    pass


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


def _is_wifi_connect_error(error):
  message = str(error)
  if message == "WiFi connect timeout":
    return True
  return message.startswith("WiFi connect failed:")


def _wifi_sync_error_result(error):
  message = str(error)
  if "STAT_NO_AP_FOUND" in message:
    return "ssid_missing"
  if "STAT_WRONG_PASSWORD" in message:
    return "password_wrong"
  return None


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
    sta.active(False)
    time.sleep_ms(200)
  sta.active(True)


async def _prepare_wifi_station_async(sta):
  import uasyncio as asyncio

  try:
    ap = network.WLAN(network.AP_IF)
    if ap.active():
      ap.active(False)
  except Exception:
    pass

  if sta.active():
    _disconnect_wifi(sta)
    sta.active(False)
    await asyncio.sleep_ms(200)
  sta.active(True)


def _connect_wifi_attempt(sta, ssid, password, timeout_s):
  _prepare_wifi_station(sta)
  scan_target = _log_wifi_scan(sta, ssid)
  _configure_wifi_target(sta, scan_target)
  print("WiFi password:", repr(password))

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

  # An explicit WLAN scan is synchronous on this MicroPython port and is not
  # required for connection. Let the station select the AP while the normal
  # status loop yields cooperatively.
  await _prepare_wifi_station_async(sta)
  print("WiFi password:", repr(password))

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
    return False, bool(rtc.update_internal_rtc_from_external()), "general_fail"

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
    return True, True, None

  except Exception as e:
    if _is_wifi_connect_error(e):
      print("Failed to connect to WiFi:", e)
    else:
      print("Error fetching time from NTP:", e)
    try:
      _reset_wifi_radio()
    except Exception as reset_ex:
      print("Radio reset failed:", reset_ex)
    return False, bool(rtc.update_internal_rtc_from_external()), _wifi_sync_error_result(e) or "general_fail"

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
    return False, bool(rtc.update_internal_rtc_from_external()), "general_fail"

  try:
    sta = network.WLAN(network.STA_IF)
    await _connect_wifi_async(sta, ssid, password, timeout_s=wifi_timeout_s)
    print("Connected to WiFi:", ssid)

    # DNS and NTP both use non-blocking UDP polling under one hard deadline,
    # keeping the Display scheduler responsive.
    utc_now = await _set_rtc_from_ntp_async(
      rtc, sta, ntp_host, ntp_timeout_s)
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
    return True, True, None

  except Exception as e:
    if _is_wifi_connect_error(e):
      print("Failed to connect to WiFi:", e)
    else:
      print("Error fetching time from NTP:", e)
    try:
      await _reset_wifi_radio_async()
    except Exception as reset_ex:
      print("Radio reset failed:", reset_ex)
    return False, bool(rtc.update_internal_rtc_from_external()), _wifi_sync_error_result(e) or "general_fail"
