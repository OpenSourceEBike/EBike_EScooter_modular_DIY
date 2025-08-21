class ErrorQueue:
    def __init__(self, maxlen=32):
        # Ring buffer + set for O(1) membership checks
        self._maxlen = int(maxlen)
        if self._maxlen <= 0:
            self._maxlen = 1
        self._buf = [None] * self._maxlen
        self._head = 0   # index of next item to get()
        self._tail = 0   # index to insert next item
        self._count = 0
        self._seen = set()

    def __len__(self):
        return self._count

    def is_empty(self):
        return self._count == 0

    def clear(self):
        # Fast reset
        self._buf = [None] * self._maxlen
        self._head = 0
        self._tail = 0
        self._count = 0
        self._seen.clear()

    def add(self, err):
        """Add an error string if not already present. Returns True if added."""
        if err is None:
            return False
        if not isinstance(err, str):
            err = str(err)
        err = err.strip()
        if not err:
            return False
        if err in self._seen:
            return False  # already queued

        # If full, drop the oldest to make space
        if self._count == self._maxlen:
            oldest = self._buf[self._head]
            if oldest is not None:
                self._seen.discard(oldest)
            self._buf[self._head] = None
            self._head = (self._head + 1) % self._maxlen
            self._count -= 1

        # Insert at tail
        self._buf[self._tail] = err
        self._tail = (self._tail + 1) % self._maxlen
        self._count += 1
        self._seen.add(err)
        return True

    def get(self):
        """Pop the oldest error string. Returns None if empty."""
        if self._count == 0:
            return None
        err = self._buf[self._head]
        self._buf[self._head] = None
        self._head = (self._head + 1) % self._maxlen
        self._count -= 1
        if err in self._seen:
            self._seen.discard(err)
        return err
