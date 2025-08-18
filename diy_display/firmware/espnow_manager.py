import time
import espnow

class ESPNOWNodeBase:
    # Error codes
    ERR_OK             = 256 * 0   # No error
    ERR_RX_TIMEOUT     = 256 * 1    # >4s without receiving any packet (sticky until clean_error)
    ERR_NO_ESPNOW      = 256 * 2    # ESPNow instance missing
    ERR_TX_EMPTY       = 256 * 4    # make_tx returned falsy payload
    ERR_TX_EXCEPTION   = 256 * 8    # Exception during send / make_tx
    ERR_RX_HANDLER_EXC = 256 * 16    # Exception inside on_rx

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

        self._buf_size = 2
        self._buf = [None] * self._buf_size
        self._buf_count = 0
        self._buf_head = 0

        self._error = self.ERR_OK           # sticky error; reset by clean_error()
        self._last_rx_ts = time.monotonic() # updated whenever a packet is received
        self._rx_timeout_s = 4              # 4 seconds threshold

    def clean_error(self):
        """Clear sticky error flag."""
        self._error = self.ERR_OK

    @property
    def error(self):
        """Current sticky error code (ERR_OK if none)."""
        return self._error

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
            # mark RX activity
            self._last_rx_ts = time.monotonic()
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
        # reset RX timer on (re)attach
        self._last_rx_ts = time.monotonic()

    def process_rx(self):
        """
        Drain and process incoming packets.
        Returns error code:
          - ERR_RX_TIMEOUT if >4s without receiving anything (sticky until clean_error()).
          - ERR_NO_ESPNOW if no espnow instance attached.
          - ERR_RX_HANDLER_EXC if on_rx raised.
          - ERR_OK when fine.
        """
        if not self._espnow:
            return self.ERR_NO_ESPNOW

        # Check for silent period first (sticky)
        now = time.monotonic()
        if (now - self._last_rx_ts) > self._rx_timeout_s:
            if self._error == self.ERR_OK:
                self._error = self.ERR_RX_TIMEOUT

        # Drain and process any available packets (non-blocking)
        self._drain_messages()

        # Process drained packets if handler set
        if self._on_rx:
            try:
                for pkt in self._iterate_buffer_oldest_first():
                    self._on_rx(pkt, self._vars)
            except Exception as e:
                print(self._name, "rx error:", e)
                return self.ERR_RX_HANDLER_EXC
        else:
            # No handler, just clear buffer
            for _ in self._iterate_buffer_oldest_first():
                pass

        return self._error if self._error != self.ERR_OK else self.ERR_OK

    def send_data(self):
        """
        Build and send payload.
        Returns error code:
          - ERR_NO_ESPNOW if no espnow instance.
          - ERR_TX_EMPTY if payload falsy.
          - ERR_TX_EXCEPTION for exceptions from make_tx or send().
          - ERR_OK on success or when no handler.
        """
        if not self._espnow:
            return self.ERR_NO_ESPNOW

        if not self._make_tx:
            return self.ERR_OK  # nothing to send, but no error either

        try:
            payload = self._make_tx(self._vars)
            if not payload:
                return self.ERR_TX_EMPTY
            self._espnow.send(payload, self._peer)
        except Exception as e:
            print(self._name, "tx error:", e)
            return self.ERR_TX_EXCEPTION

        return self.ERR_OK


class ESPNOWManager:
    def __init__(self, channel=1):
        self._espnow = None
        self._channel = channel
        self._nodes = []

    def add_node(self, node: ESPNOWNodeBase):
        self._nodes.append(node)
        if self._espnow:
            node.attach(self._espnow, self._channel)

    def start(self, esp_instance=None):
        new_esp = esp_instance or self._espnow or espnow.ESPNow()
        self._espnow = new_esp
        for n in self._nodes:
            n.attach(self._espnow, self._channel)

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

    @property
    def espnow(self):
        return self._espnow
