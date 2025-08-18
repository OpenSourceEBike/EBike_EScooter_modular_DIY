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

        self._buf_size = 5
        self._buf = [None] * self._buf_size
        self._buf_count = 0
        self._buf_head = 0

    def _push_pkt(self, pkt):
        self._buf[self._buf_head] = pkt
        self._buf_head = (self._buf_head + 1) % self._buf_size
        if self._buf_count < self._buf_size:
            self._buf_count += 1

    def _drain_messages(self):
        while self._espnow is not None:
            pkt = self._espnow.read()
            if pkt is None:
                break
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
        if not self._espnow or not self._on_rx:
            return

        self._drain_messages()

        for pkt in self._iterate_buffer_oldest_first():
            try:
                self._on_rx(pkt, self._vars)
            except Exception as e:
                print(self._name, "rx error:", e)

    def send_data(self):
        if not self._espnow or not self._make_tx:
            return
        try:
            payload = self._make_tx(self._vars)
            if payload:
                self._espnow.send(payload, self._peer)
        except Exception as e:
            print(self._name, "tx error:", e)


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