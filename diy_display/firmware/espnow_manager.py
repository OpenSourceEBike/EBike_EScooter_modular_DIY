import time
import espnow

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
        self._buf_size = 5
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
        """Non-blocking drain of all queued packets from ESPNow into ring buffer."""
        while self._espnow is not None:
            pkt = self._espnow.read()
            if pkt is None:
                break
            # notify manager we had RX activity
            if self._manager is not None:
                self._manager.note_rx_activity()
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
        new_channel = channel or self._channel

        if self._attached_espnow is esp and self._peer is not None and new_channel == self._channel:
            return

        if self._attached_espnow and self._peer:
            try:
                self._attached_espnow.peers.remove(self._peer)
            except Exception:
                pass

        self._espnow = esp
        self._channel = new_channel
        self._peer = espnow.Peer(mac=self._mac, channel=self._channel)

        try:
            if not any(getattr(p, "mac", None) == self._mac for p in self._espnow.peers):
                self._espnow.peers.append(self._peer)
        except Exception:
            self._espnow.peers.append(self._peer)

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

    def send_data(self):
        """Build and send payload."""
        if not self._espnow or not self._make_tx:
            return
        
        payload = self._make_tx(self._vars)
        if not payload:
            return
        if isinstance(payload, str):
            payload = payload.encode("utf-8")   # <-- ensure bytes
        self._espnow.send(payload, self._peer)

class ESPNOWManager:
    # ---- Global (static) error codes ----
    ERR_OK         = 0
    ERR_RX_TIMEOUT = 1 << 0  # no RX for timeout window

    # global sticky bitmask shared by all instances
    _GLOBAL_ERROR = ERR_OK

    @classmethod
    def _set_error(cls, mask):
        cls._GLOBAL_ERROR |= mask

    @classmethod
    def get_error(cls):
        """Return global sticky error bitmask."""
        return cls._GLOBAL_ERROR

    @classmethod
    def clear_error(cls):
        """Clear global sticky error bitmask."""
        cls._GLOBAL_ERROR = cls.ERR_OK

    def __init__(self, channel=1, rx_timeout_s=5):
        self._espnow = None
        self._channel = channel
        self._nodes = []

        # RX timeout window (per-manager timer, but error is global)
        self._rx_timeout_s = rx_timeout_s
        self._last_rx_ts = time.monotonic()

    def add_node(self, node: ESPNOWNodeBase):
        self._nodes.append(node)
        node._manager = self  # set back-reference
        if self._espnow:
            node.attach(self._espnow, self._channel)

    def start(self, esp_instance=None):
        new_esp = esp_instance or self._espnow or espnow.ESPNow()
        self._espnow = new_esp
        for n in self._nodes:
            n.attach(self._espnow, self._channel)
        self._last_rx_ts = time.monotonic()

    def restart(self, esp_instance=None, channel=None):
        self._channel = channel or self._channel
        try:
            if self._espnow and hasattr(self._espnow, "deinit"):
                self._espnow.deinit()
        except Exception as e:
            print("ESPNow deinit warning:", e)

        self._espnow = esp_instance or espnow.ESPNow()
        for n in self._nodes:
            n.attach(self._espnow, self._channel)
        # reset silence timer so we don’t loop-restart instantly
        self._last_rx_ts = time.monotonic()

    # --- Global RX silence management ---

    def note_rx_activity(self):
        """Called by nodes whenever a packet is received."""
        self._last_rx_ts = time.monotonic()

    def tick(self):
        """
        Call this periodically (e.g., each loop iteration).
        If there's been no RX for > rx_timeout_s, set GLOBAL sticky error and restart ESPNow.
        """
        if (time.monotonic() - self._last_rx_ts) > self._rx_timeout_s:
            # mark global sticky error and restart
            ESPNOWManager._set_error(ESPNOWManager.ERR_RX_TIMEOUT)
            self.restart()  # deinit + init

    # --- Instance-level convenience proxies (optional) ---

    @property
    def error(self):
        """Instance proxy to global error bitmask."""
        return ESPNOWManager.get_error()

    def clear_error(self):
        """Instance proxy to clear global error bitmask."""
        ESPNOWManager.clear_error()

    @property
    def espnow(self):
        return self._espnow
