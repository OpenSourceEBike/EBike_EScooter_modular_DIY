import network
import espnow

_ESPNOW_MAX_PENDING_PACKETS = 5
_ESPNOW_PENDING_BY_ESP_ID = {}


def espnow_init(channel: int, local_mac):
  """
  Initialize Wi-Fi STA/AP and ESP-NOW and return (sta, esp).
  """
  sta = network.WLAN(network.STA_IF)
  if not sta.active():
    sta.active(True)
  try:
    try:
      sta.disconnect()
    except Exception:
      pass
    sta.config(channel=channel)
  except Exception:
    pass
  try:
    ap = network.WLAN(network.AP_IF)
    if ap.active():
      ap.active(False)
  except Exception:
    pass

  if local_mac is not None:
    try:
      sta.config(mac=bytes(local_mac))
    except Exception as ex:
      print("Warning: couldn't fix local MAC:", ex)

  esp = espnow.ESPNow()
  esp.active(True)
  return sta, esp


def espnow_recv_last(esp):
  """Drain the ESP-NOW queue and return the oldest packet among the latest five."""
  pending = _ESPNOW_PENDING_BY_ESP_ID.get(id(esp))
  if pending is None:
    pending = []
    _ESPNOW_PENDING_BY_ESP_ID[id(esp)] = pending

  try:
    while True:
      host, msg = esp.recv(0)
      if not msg:
        break
      pending.append((host, msg))
      while len(pending) > _ESPNOW_MAX_PENDING_PACKETS:
        pending.pop(0)
  except OSError:
    pass
  except Exception as ex:
    print("ESP-NOW recv error:", ex)
    return None

  if not pending:
    return None

  return pending.pop(0)


def espnow_recv_all(esp):
  """Drain the ESP-NOW queue and return all (host, msg) packets seen."""
  packets = []
  try:
    while True:
      host, msg = esp.recv(0)
      if not msg:
        break
      packets.append((host, msg))
  except OSError:
    pass
  except Exception as ex:
    print("ESP-NOW recv error:", ex)
    return []
  return packets


class ESPNowComms:
  def __init__(self, espnow_inst, peer, decoder=None, encoder=None):
    self._esp = espnow_inst
    self._decoder = decoder
    self._encoder = encoder
    if peer is None:
      raise ValueError("ESPNowComms requires a peer MAC")
    self._peer = peer
    self._peer_added = False
    self._had_send_failure = False
    self._had_send_success = False
    self._pending_packets = []
    try:
      self._esp.add_peer(peer)
      self._peer_added = True
    except OSError as e:
      if e.args and e.args[0] == -12395:
        self._peer_added = True
      else:
        print("ESP-NOW add_peer error:", e)

  def get_data(self):
    packet = self.get_data_with_host()
    if packet is None:
      return None
    _, decoded = packet
    return decoded

  def get_data_with_host(self):
    try:
      while True:
        host, msg = self._esp.recv(0)
        if not msg:
          break
        self._pending_packets.append((host, msg))
        while len(self._pending_packets) > _ESPNOW_MAX_PENDING_PACKETS:
          self._pending_packets.pop(0)
    except OSError:
      pass
    except Exception as ex:
      print("ESP-NOW recv error:", ex)
      return None

    while self._pending_packets:
      host, last_msg = self._pending_packets.pop(0)
      if not last_msg:
        continue

      if self._decoder is None:
        return (host, None)

      try:
        decoded = self._decoder(last_msg)
      except Exception as ex:
        print("ESP-NOW decode error:", ex)
        return None

      if decoded is None:
        continue

      return (host, decoded)

    return None

  def send_data(self, *args):
    payload = self._encoder(*args)

    def _send_once():
      if not self._peer_added:
        return False
      try:
        return self._esp.send(self._peer, payload)
      except OSError as e:
        if e.args and e.args[0] == 116:
          return False
        raise

    try:
      ok = _send_once()
      if ok is False:
        if not self._had_send_failure:
          print("ESP-NOW tx error to peer {}".format(self._peer))
          self._had_send_failure = True
          self._had_send_success = False
        return False
      self._had_send_failure = False
      if not self._had_send_success:
        print("ESP-NOW tx ok to peer {}".format(self._peer))
        self._had_send_success = True
      return True
    except OSError as e:
      if not (e.args and e.args[0] == 116):
        print("ESP-NOW tx error:", e)
      return False
    except Exception as e:
      print("ESP-NOW tx error:", e)
      return False
