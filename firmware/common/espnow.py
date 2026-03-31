import network
import espnow


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
    try:
      self._esp.add_peer(peer)
      self._peer_added = True
    except OSError as e:
      if e.args and e.args[0] == -12395:
        self._peer_added = True
      else:
        print("ESP-NOW add_peer error:", e)

  def get_data(self):
    last_msg = None
    try:
      while True:
        host, msg = self._esp.recv(0)
        if not msg:
          break
        last_msg = msg
    except OSError:
      pass
    except Exception as ex:
      print("ESP-NOW recv error:", ex)
      return None

    if not last_msg:
      return None

    if self._decoder is None:
      return None

    try:
      decoded = self._decoder(last_msg)
    except Exception as ex:
      print("ESP-NOW decode error:", ex)
      return None

    return decoded

  def send_data(self, *args):
    payload = self._encoder(*args)
    try:
      if not self._peer_added:
        if not self._had_send_failure:
          print("ESP-NOW tx error to peer {}".format(self._peer))
          self._had_send_failure = True
          self._had_send_success = False
        return False
      ok = self._esp.send(self._peer, payload)
      if ok is False:
        if not self._had_send_failure:
          print("ESP-NOW tx error to peer {}".format(self._peer))
          self._had_send_failure = True
          self._had_send_success = False
      else:
        self._had_send_failure = False
        if not self._had_send_success:
          print("ESP-NOW tx ok to peer {}".format(self._peer))
          self._had_send_success = True
    except OSError as e:
      if not (e.args and e.args[0] == 116):
        print("ESP-NOW tx error:", e)
    except Exception as e:
      print("ESP-NOW tx error:", e)
