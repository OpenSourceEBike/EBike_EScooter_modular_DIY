import network
import espnow
import urandom

def espnow_jittered_period_ms(period_ms, jitter_ms=20):
  """Return a bounded random period for periodic ESP-NOW transmissions."""
  if jitter_ms <= 0:
    return period_ms
  offset = (urandom.getrandbits(8) % (2 * jitter_ms + 1)) - jitter_ms
  return max(1, period_ms + offset)


def configure_wifi_radio(sta, tx_power_dbm, label, debug=False):
  """Apply and report WiFi radio settings for a board."""
  if not debug:
    sta.config(txpower=tx_power_dbm)
    try:
      sta.config(pm=sta.PM_NONE)
    except (AttributeError, OSError, ValueError):
      pass
    return
  try:
    print("WiFi TX power before ({}): {} dBm".format(label, sta.config("txpower")))
  except (AttributeError, OSError, ValueError):
    print("WiFi TX power before ({}): unavailable".format(label))

  try:
    print("WiFi TX power config ({}): {} dBm".format(label, tx_power_dbm))
    sta.config(txpower=tx_power_dbm)
    print("WiFi TX power applied ({}): {} dBm".format(label, sta.config("txpower")))
  except (AttributeError, OSError, ValueError):
    print("WiFi TX power configuration not supported ({})".format(label))

  try:
    sta.config(pm=sta.PM_NONE)
  except (AttributeError, OSError, ValueError):
    pass


def espnow_init(channel: int, local_mac, debug=False, strict=False):
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
  except Exception as ex:
    if debug:
      print("ESP-NOW channel setup error:", ex)
    if strict:
      raise
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
      if debug:
        print("Warning: couldn't fix local MAC:", ex)

  esp = espnow.ESPNow()
  esp.active(True)
  return sta, esp


def espnow_recv_all(esp, debug=False):
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
    if debug:
      print("ESP-NOW recv error:", ex)
    return []
  return packets


class ESPNowComms:
  def __init__(self, espnow_inst, peer, decoder=None, encoder=None, debug=False):
    self._esp = espnow_inst
    self._decoder = decoder
    self._encoder = encoder
    self._debug = bool(debug)
    if peer is None:
      raise ValueError("ESPNowComms requires a peer MAC")
    self._peer = peer
    self._peer_added = False
    self._had_send_failure = False
    self._had_send_success = False
    try:
      self._esp.add_peer(peer)
      self._peer_added = True
    except OSError as e:
      if e.args and e.args[0] == -12395:
        self._peer_added = True
      elif self._debug:
        print("ESP-NOW add_peer error:", e)

  @property
  def peer_ready(self):
    return self._peer_added

  def _ensure_peer(self):
    if self._peer_added:
      return True
    try:
      self._esp.add_peer(self._peer)
      self._peer_added = True
      if self._debug:
        print("ESP-NOW peer added:", self._peer)
    except OSError as e:
      if e.args and e.args[0] == -12395:
        self._peer_added = True
      elif self._debug:
        print("ESP-NOW add_peer error for {}: {}".format(self._peer, e))
    except Exception as e:
      if self._debug:
        print("ESP-NOW add_peer error for {}: {}".format(self._peer, e))
    return self._peer_added

  def get_latest_data_by_source(self):
    """Drain the receive queue and keep only the latest packet per source."""
    latest_by_source = {}

    try:
      while True:
        host, msg = self._esp.recv(0)
        if not msg:
          break

        if self._decoder is None:
          continue

        try:
          decoded = self._decoder(msg)
        except Exception as ex:
          if self._debug:
            print("ESP-NOW decode error:", ex)
          continue

        if decoded is None:
          continue

        # The unified protocol stores the source board at index 1.
        try:
          source = decoded[1]
        except (IndexError, TypeError):
          continue
        latest_by_source[source] = (host, decoded)
    except OSError:
      pass
    except Exception as ex:
      if self._debug:
        print("ESP-NOW recv error:", ex)
      return latest_by_source

    return latest_by_source

  def get_latest_data_with_host(self):
    """Drain the receive queue and return only the latest valid decoded packet."""
    latest_packet = None

    try:
      while True:
        host, msg = self._esp.recv(0)
        if not msg:
          break

        if self._decoder is None:
          continue

        try:
          decoded = self._decoder(msg)
        except Exception as ex:
          if self._debug:
            print("ESP-NOW decode error:", ex)
          continue

        if decoded is not None:
          latest_packet = (host, decoded)
    except OSError:
      pass
    except Exception as ex:
      if self._debug:
        print("ESP-NOW recv error:", ex)

    return latest_packet

  def send_data(self, *args):
    payload = self._encoder(*args)

    def _send_once():
      if not self._ensure_peer():
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
          if self._debug:
            print("ESP-NOW tx error to peer {}".format(self._peer))
          self._had_send_failure = True
          self._had_send_success = False
        return False
      self._had_send_failure = False
      if not self._had_send_success:
        if self._debug:
          print("ESP-NOW tx ok to peer {}".format(self._peer))
        self._had_send_success = True
      return True
    except OSError as e:
      if self._debug and not (e.args and e.args[0] == 116):
        print("ESP-NOW tx error:", e)
      return False
    except Exception as e:
      if self._debug:
        print("ESP-NOW tx error:", e)
      return False
