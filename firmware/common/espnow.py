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
  def __init__(self, espnow_inst, decoder=None, encoder=None):
    self._esp = espnow_inst
    self._decoder = decoder
    self._encoder = encoder

  def get_data(self):
    last_msg = None
    try:
      while True:
        host, msg = self._esp.recv(0)
        if not msg:
          break
        last_msg = msg
        try:
          self._esp.add_peer(host)
        except OSError:
          pass
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

  def send_data(self, peer_mac, *args):
    if self._encoder is None:
      raise ValueError("ESPNowComms encoder is not set")

    payload = self._encoder(*args)
    try:
      ok = self._esp.send(peer_mac, payload)
      if ok is False:
        try:
          self._esp.add_peer(peer_mac)
        except OSError:
          pass
        try:
          self._esp.send(peer_mac, payload)
        except Exception:
          pass
    except OSError as e:
      if not (e.args and e.args[0] == 116):
        print("ESP-NOW tx error:", e)
    except Exception as e:
      print("ESP-NOW tx error:", e)
