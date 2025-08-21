import time
import errno
import espnow
import gc

# Optional: if available, we use it to fully cycle the radio on hard resets
try:
    import wifi
except Exception:
    wifi = None

# ==============================
# ESP-NOW Singleton (inline)
# ==============================
class _ESPNowSingleton:
    _ESP = None

    @classmethod
    def get(cls):
        """Return the single ESP-NOW instance, creating if needed."""
        if cls._ESP is None:
            cls._ESP = espnow.ESPNow()
        return cls._ESP

    @classmethod
    def ensure_reset(cls, wait_ms=80):
        """
        Fully reset the ESP-NOW stack and return a fresh instance.
        Safe to call even if no instance exists.
        """
        # Best-effort clean shutdown of previous instance
        try:
            if cls._ESP is not None and hasattr(cls._ESP, "deinit"):
                try:
                    cls._ESP.deinit()
                except Exception:
                    pass
        finally:
            cls._ESP = None

        # Optionally cycle the radio to release lower layers
        if wifi is not None:
            try:
                wifi.radio.enabled = False
            except Exception:
                pass
            time.sleep(wait_ms / 1000.0)
            try:
                wifi.radio.enabled = True
            except Exception:
                pass
            time.sleep(wait_ms / 1000.0)

        gc.collect()
        cls._ESP = espnow.ESPNow()
        return cls._ESP


class ESPNOWNodeBase:
    def __init__(self, mac_address, vars, *, on_rx=None, make_tx=None, channel=1, name="Node"):
        self._mac = bytes(mac_address)
        self._vars = vars
        self._on_rx = on_rx
        self._make_tx = make_tx
        self._channel = channel
        self._name = name
        self._espnow = None
        self._peer = None
        self._attached_espnow = None

        # ring buffer
        self._buf_size = 2
        self._buf = [None] * self._buf_size
        self._buf_count = 0
        self._buf_head = 0

        # manager back-reference (set by ESPNOWManager.add_node)
        self._manager = None

    def _push_pkt(self, pkt):
        self._buf[self._buf_head] = pkt
        self._buf_head = (self._buf_head + 1) % self._buf_size
        if self._buf_count < self._buf_size:
            self._buf_count += 1

    def _drain_messages(self):
        while self._espnow is not None:
            try:
                raw = self._espnow.read()
            except Exception:
                break

            if raw is None:
                break

            try:
                if isinstance(raw, tuple) and len(raw) == 2:
                    mac, payload = raw
                    mac_b = bytes(mac)
                    payload_b = bytes(payload)  # copy to avoid reused buffers
                    pkt = (mac_b, payload_b)
                else:
                    mac = getattr(raw, "mac", None)
                    if mac is None:
                        continue
                    msg_or_payload = getattr(raw, "msg", None)
                    if msg_or_payload is None:
                        msg_or_payload = getattr(raw, "payload", None)
                    if msg_or_payload is None:
                        continue
                    mac_b = bytes(mac)
                    payload_b = bytes(msg_or_payload)  # copy
                    pkt = (mac_b, payload_b)
            except Exception:
                continue

            # notify manager we had RX activity
            if self._manager is not None:
                try:
                    self._manager.note_rx_activity()
                except Exception:
                    pass

            self._push_pkt(pkt)

    def _iterate_buffer_oldest_first(self):
        n = self._buf_count
        if n == 0:
            return
        start = (self._buf_head - n) % self._buf_size
        for i in range(n):
            idx = (start + i) % self._buf_size
            pkt = self._buf[idx]
            if pkt is not None:
                yield pkt
        self._buf_count = 0

    def attach(self, esp, channel=None):
        """
        Attach to (singleton) ESP-NOW instance and (re)create our peer entry.
        Idempotent and safe after restarts.
        """
        new_channel = channel or self._channel

        # If nothing changed (same esp handle, peer exists, same channel), do nothing.
        if (self._attached_espnow is esp) and (self._peer is not None) and (new_channel == self._channel):
            return

        # Try to remove old peer from previous instance (if list API exists).
        if (self._attached_espnow is not None) and (self._peer is not None):
            try:
                peers = getattr(self._attached_espnow, "peers", None)
                if peers:
                    try:
                        peers.remove(self._peer)
                    except Exception:
                        pass
            except Exception:
                # old handle may be deinitialized; ignore
                pass

        self._espnow = esp
        self._channel = new_channel
        self._peer = espnow.Peer(mac=self._mac, channel=self._channel)

        # Append peer if not already present
        try:
            peers = getattr(self._espnow, "peers", None)
            if peers is not None:
                # only append if same MAC not already present
                if not any(getattr(p, "mac", None) == self._mac for p in peers):
                    peers.append(self._peer)
        except Exception:
            try:
                # some builds expose peers only as attribute
                self._espnow.peers.append(self._peer)
            except Exception:
                pass

        self._attached_espnow = esp

    def process_rx(self):
        """Drain and process incoming packets."""
        if not self._espnow:
            return

        self._drain_messages()

        if self._on_rx:
            for pkt in self._iterate_buffer_oldest_first():
                self._on_rx(pkt, self._vars)
        else:
            for _ in self._iterate_buffer_oldest_first():
                pass

    def _ensure_peer_attached(self):
        """Ensure our peer exists in espnow.peers (can be lost after resets)."""
        try:
            peers = getattr(self._espnow, "peers", None)
            if peers is None:
                return True  # some builds don't expose a list
            if any(getattr(p, "mac", None) == self._mac for p in peers):
                return True
            # (Re)create and append
            self._peer = espnow.Peer(mac=self._mac, channel=self._channel)
            peers.append(self._peer)
            return True
        except Exception:
            return False

    def send_data(self):
        """Build and send payload (single attempt, no retries)."""
        if not self._espnow or not self._make_tx or not self._peer:
            return

        payload = self._make_tx(self._vars)
        if not payload:
            return

        # Normalize to bytes (immutable/contiguous)
        if isinstance(payload, str):
            msg = payload.encode("ascii", "strict")
        elif isinstance(payload, (bytes, bytearray, memoryview)):
            msg = bytes(payload)
        else:
            msg = str(payload).encode("ascii", "strict")

        # Best-effort ensure peer exists before sending (no retry)
        self._ensure_peer_attached()

        try:
            # fixed signature: send(payload, peer)
            self._espnow.send(msg, self._peer)

        except OSError as e:
            err = getattr(e, "errno", None)

            if err == errno.EINVAL:
                # peer missing; fix for NEXT call (no resend)
                self._ensure_peer_attached()

            elif err in (getattr(errno, "ENODEV", -19),
                         getattr(errno, "ESHUTDOWN", -108)):
                # local radio dead; ask manager to restart (no resend)
                if self._manager:
                    try:
                        self._manager.restart(hard=True)
                    except Exception:
                        pass
            # EBUSY/EAGAIN/etc: drop this attempt silently

        except Exception:
            # Any other transient error: drop this attempt
            pass


class ESPNOWManager:
    # ---- Global (static) error codes ----
    ERR_OK      = 0
    ERR_RX_FAIL = 1 << 0  # no RX for timeout window (link down)
    ERR_TX_FAIL = 1 << 1  # send_failure increased (bit 1, contiguous)

    _GLOBAL_ERROR = ERR_OK  # sticky

    @classmethod
    def _set_error(cls, mask):
        cls._GLOBAL_ERROR |= mask

    @classmethod
    def get_error(cls):
        return cls._GLOBAL_ERROR

    @classmethod
    def clear_error(cls):
        cls._GLOBAL_ERROR = cls.ERR_OK

    def __init__(self, channel=1, rx_timeout_s=5, tx_timeout_s=5.0):
        self._espnow = None
        self._channel = channel
        self._nodes = []

        # RX silence detector (link down)
        self._rx_timeout_s = rx_timeout_s
        self._last_rx_ts = time.monotonic()

        # TX failure monitoring
        self._tx_timeout_s = tx_timeout_s
        self._last_send_ok = 0
        self._last_send_fail = 0
        self._first_fail_ts = None   # when a failure streak started
        self._last_restart_ts = 0.0  # avoid fast restart loops
        self._restart_min_interval_s = 2.0

        # Re-entrancy guard for restart
        self._restarting = False

    def _refresh_counter_baseline(self):
        e = self._espnow
        if not e:
            self._last_send_ok = self._last_send_fail = 0
            self._first_fail_ts = None
            return
        self._last_send_ok   = getattr(e, "send_success", 0)
        self._last_send_fail = getattr(e, "send_failure", 0)
        self._first_fail_ts  = None

    def _poll_espnow_counters(self):
        """Track TX success/failure and start/clear failure streaks. Set sticky ERR_TX_FAIL on new failures."""
        e = self._espnow
        if not e:
            return

        now = time.monotonic()
        send_ok   = getattr(e, "send_success", 0)
        send_fail = getattr(e, "send_failure", 0)

        # Any new success breaks the failure streak
        if send_ok > self._last_send_ok:
            self._first_fail_ts = None

        # Any new failure: set error bit and (if no streak) start one
        if send_fail > self._last_send_fail:
            ESPNOWManager._set_error(ESPNOWManager.ERR_TX_FAIL)
            if self._first_fail_ts is None:
                self._first_fail_ts = now

        # If failure streak has lasted long enough, restart once
        if (self._first_fail_ts is not None and
            (now - self._first_fail_ts) > self._tx_timeout_s and
            (now - self._last_restart_ts) > self._restart_min_interval_s):
            self.restart(hard=False)
            self._last_restart_ts = now

        # Update baselines
        self._last_send_ok   = send_ok
        self._last_send_fail = send_fail

    def add_node(self, node: ESPNOWNodeBase):
        self._nodes.append(node)
        node._manager = self
        if self._espnow:
            node.attach(self._espnow, self._channel)

    def start(self, esp_instance=None):
        """
        Start or attach to ESP-NOW. Never creates a second instance.
        """
        if esp_instance is not None:
            # Use provided instance (assumed live)
            self._espnow = esp_instance
        else:
            # Use singleton (creates only if needed)
            self._espnow = _ESPNowSingleton.get()

        for n in self._nodes:
            n.attach(self._espnow, self._channel)
        self._last_rx_ts = time.monotonic()
        self._refresh_counter_baseline()

    def restart(self, esp_instance=None, channel=None, hard=False):
        """
        Restart the ESP-NOW stack safely.
        - hard=True does a full deinit/radio cycle/new instance.
        - hard=False reuses the singleton (clears peers and reattaches).
        Never creates a second instance in parallel.
        """
        if self._restarting:
            return
        now = time.monotonic()
        if (now - self._last_restart_ts) < self._restart_min_interval_s:
            return

        self._restarting = True
        self._last_restart_ts = now
        try:
            self._channel = channel or self._channel

            # Invalidate node handles first
            for n in self._nodes:
                n._attached_espnow = None
                n._peer = None

            if esp_instance is not None:
                # Caller explicitly provides one; adopt it
                self._espnow = esp_instance
            else:
                if hard:
                    # Full reset + fresh instance
                    self._espnow = _ESPNowSingleton.ensure_reset(wait_ms=80)
                else:
                    # Reuse the singleton (creates if needed)
                    try:
                        self._espnow = _ESPNowSingleton.get()
                    except RuntimeError as e:
                        # Handle "Already running" by reusing current singleton
                        if "Already running" in str(e):
                            self._espnow = _ESPNowSingleton.get()
                        else:
                            raise

            # Reattach nodes (this recreates peers)
            for n in self._nodes:
                n.attach(self._espnow, self._channel)

            self._last_rx_ts = time.monotonic()
            self._refresh_counter_baseline()

        finally:
            self._restarting = False
            gc.collect()

    def note_rx_activity(self):
        """Called by nodes whenever a packet is received."""
        self._last_rx_ts = time.monotonic()

    def tick(self):
        """
        Call this periodically:
        - Restart if no RX for > rx_timeout_s (link down).
        - Restart if TX failures keep happening for > tx_fail_timeout_s.
        """
        now = time.monotonic()

        if self._rx_timeout_s and (now - self._last_rx_ts) > self._rx_timeout_s:
            ESPNOWManager._set_error(ESPNOWManager.ERR_RX_FAIL)
            if (now - self._last_restart_ts) > self._restart_min_interval_s:
                # Soft restart first (reuse singleton)
                self.restart(hard=False)

        self._poll_espnow_counters()

    # --- Instance-level convenience proxies ---

    @property
    def error(self):
        return ESPNOWManager.get_error()

    @property
    def espnow(self):
        return self._espnow
