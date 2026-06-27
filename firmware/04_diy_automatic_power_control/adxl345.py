from machine import I2C, Pin


class ADXL345:
    _ADDR = 0x53
    _REG_BW_RATE = 0x2C
    _REG_POWER_CTL = 0x2D
    _REG_INT_ENABLE = 0x2E
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

    def setup_motion_detection(
        self,
        threshold: int = 8,
        rate_hz: int = 100,
        ac_mode: bool = True,
    ):
        threshold = self.normalize_motion_threshold(threshold)
        supported_rate = self.normalize_motion_rate_hz(rate_hz)
        rate_code = self._RATE_CODES[supported_rate]

        # Output data rate
        self._write8(self._REG_BW_RATE, rate_code)

        # Full resolution, +/-2g
        self._write8(self._REG_DATA_FORMAT, 0x08)

        # Activity threshold
        self._write8(self._REG_THRESH_ACT, threshold & 0xFF)

        # Activity on X/Y/Z
        # DC mode: 0x70
        # AC mode: 0xF0
        self._write8(self._REG_ACT_INACT_CTL, 0xF0 if ac_mode else 0x70)

        # Enable only activity interrupt
        self._write8(self._REG_INT_ENABLE, self._INT_ACTIVITY)

        # Measure mode
        self._write8(self._REG_POWER_CTL, 0x08)

        # Clear pending interrupts once
        self._read8(self._REG_INT_SOURCE)

    def motion_detected(self) -> bool:
        if not self._int_pin.value():
            return False

        src = self._read8(self._REG_INT_SOURCE)
        return bool(src & self._INT_ACTIVITY)
