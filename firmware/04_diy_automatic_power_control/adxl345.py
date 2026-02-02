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

  def __init__(self, i2c: I2C, int_pin: int, address: int = _ADDR):
    self._i2c = i2c
    self._addr = address
    self._int_pin = Pin(int_pin, Pin.IN)

  def _write8(self, reg, val):
    self._i2c.writeto_mem(self._addr, reg, bytes([val & 0xFF]))

  def _read8(self, reg):
    return self._i2c.readfrom_mem(self._addr, reg, 1)[0]

  def setup_motion_detection(self, threshold: int = 16):
    # 100 Hz output data rate
    self._write8(self._REG_BW_RATE, 0x0A)
    # Full resolution, +/-2g
    self._write8(self._REG_DATA_FORMAT, 0x08)
    # Activity threshold
    self._write8(self._REG_THRESH_ACT, threshold & 0xFF)
    # Enable activity detection on X/Y/Z (AC mode)
    self._write8(self._REG_ACT_INACT_CTL, 0x07)
    # Enable activity interrupt
    self._write8(self._REG_INT_ENABLE, self._INT_ACTIVITY)
    # Measure mode
    self._write8(self._REG_POWER_CTL, 0x08)
    # Clear any pending interrupt
    self._read8(self._REG_INT_SOURCE)

  def motion_detected(self) -> bool:
    if self._int_pin.value():
      src = self._read8(self._REG_INT_SOURCE)
      return bool(src & self._INT_ACTIVITY)
    return False
