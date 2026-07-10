from machine import I2C, Pin


class ADXL345:
    _ADDR = 0x53
    _ADDR_ALT = 0x1D
    _REG_DEVID = 0x00
    _REG_BW_RATE = 0x2C
    _REG_POWER_CTL = 0x2D
    _REG_INT_ENABLE = 0x2E
    _REG_INT_MAP = 0x2F
    _REG_INT_SOURCE = 0x30
    _REG_DATA_FORMAT = 0x31
    _REG_THRESH_ACT = 0x24
    _REG_ACT_INACT_CTL = 0x27

    _INT_ACTIVITY = 0x10
    _THRESHOLD_MIN = 0
    _THRESHOLD_MAX = 255
    _RATE_CODES = {
        3200: 0x0F,
        1600: 0x0E,
        800: 0x0D,
        400: 0x0C,
        200: 0x0B,
        100: 0x0A,
        50: 0x09,
        25: 0x08,
        12: 0x07,
        6: 0x06,
        3: 0x05,
    }

    def __init__(self, i2c: I2C, int_pin: int, address: int = _ADDR):
        self._i2c = i2c
        self._addr = address
        self._int_pin = Pin(int_pin, Pin.IN)
        self._last_int_state = 0
        self._motion_latched = False
        self.events = _ADXL345Events(self)
        dev_id = self._read8(self._REG_DEVID)
        if dev_id != 0xE5:
            raise RuntimeError(
                f"ADXL345 not found at {hex(self._addr)}, DEVID={hex(dev_id)}"
            )

    def _write8(self, reg, val):
        self._i2c.writeto_mem(self._addr, reg, bytes([val & 0xFF]))

    def _read8(self, reg):
        return self._i2c.readfrom_mem(self._addr, reg, 1)[0]

    @classmethod
    def normalize_motion_threshold(cls, threshold: int) -> int:
        threshold = int(threshold)
        if threshold < cls._THRESHOLD_MIN or threshold > cls._THRESHOLD_MAX:
            raise ValueError(
                f"threshold must be between {cls._THRESHOLD_MIN} and {cls._THRESHOLD_MAX}"
            )
        return threshold

    @classmethod
    def normalize_motion_rate_hz(cls, rate_hz: int) -> int:
        rate_hz = int(rate_hz)
        if rate_hz <= 0:
            raise ValueError("rate_hz must be > 0")
        return min(
            cls._RATE_CODES,
            key=lambda supported: abs(supported - rate_hz),
        )

    def enable_motion_detection(
        self,
        threshold: int = 18,
        rate_hz: int = 100,
        ac_mode: bool = False,
    ):
        threshold = self.normalize_motion_threshold(threshold)
        supported_rate = self.normalize_motion_rate_hz(rate_hz)
        rate_code = self._RATE_CODES[supported_rate]

        # Put device in standby while reconfiguring.
        self._write8(self._REG_POWER_CTL, 0x00)
        self._write8(self._REG_INT_ENABLE, 0x00)

        # Output data rate
        self._write8(self._REG_BW_RATE, rate_code)

        # Full resolution, +/-2g
        self._write8(self._REG_DATA_FORMAT, 0x08)

        # Activity on X/Y/Z, matching the CircuitPython driver by default.
        # Bit 7 selects AC-coupled activity detection. Keeping it configurable
        # lets the power board preserve the requested mode from config.
        act_inact_ctl = 0x70
        if ac_mode:
            act_inact_ctl |= 0x80
        self._write8(self._REG_ACT_INACT_CTL, act_inact_ctl)

        # Activity threshold
        self._write8(self._REG_THRESH_ACT, threshold & 0xFF)

        # Route activity to INT1 explicitly so wake detection matches the wired pin.
        int_map = self._read8(self._REG_INT_MAP)
        int_map &= ~self._INT_ACTIVITY
        self._write8(self._REG_INT_MAP, int_map)

        # This firmware only uses the activity interrupt.
        self._write8(self._REG_INT_ENABLE, self._INT_ACTIVITY)

        # Measure mode
        self._write8(self._REG_POWER_CTL, 0x08)

        # Clear pending interrupts once
        self._read8(self._REG_INT_SOURCE)
        self._last_int_state = 0
        self._motion_latched = False

    def _motion_event(self) -> bool:
        current_int_state = 1 if self._int_pin.value() else 0
        if not current_int_state:
            self._last_int_state = 0
            self._motion_latched = False
            return False

        src = self._read8(self._REG_INT_SOURCE)
        active = bool(src & self._INT_ACTIVITY)
        if not active:
            self._motion_latched = False
            return False

        if self._last_int_state and self._motion_latched:
            return False

        self._last_int_state = 1
        self._motion_latched = True
        return True

    def setup_motion_detection(self, threshold: int = 18, rate_hz: int = 100, ac_mode: bool = False):
        # Compatibility wrapper for the existing power-board code.
        self.enable_motion_detection(
            threshold=threshold,
            rate_hz=rate_hz,
            ac_mode=ac_mode,
        )

    def motion_detected(self) -> bool:
        return self._motion_event()


class _ADXL345Events:
    def __init__(self, sensor: ADXL345):
        self._sensor = sensor

    def get(self, name):
        if name == "motion":
            return self._sensor._motion_event()
        raise KeyError(name)
