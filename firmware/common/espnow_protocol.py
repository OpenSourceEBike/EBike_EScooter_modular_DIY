"""Shared ESPNOW frame helpers for the firmware."""

BOARD_DISPLAY = 1
BOARD_MOTOR = 2
BOARD_LIGHTS = 3
BOARD_POWER_SWITCH = 4

MSG_COMMAND = 1
MSG_STATUS = 2

HEALTH_MOTOR_LIGHTS_TX_OK = 1 << 0
HEALTH_MOTOR_REAR_SPEED_VALID = 1 << 4

POWER_SWITCH_CMD = 1
POWER_CONFIG_CMD = 2


def _encode(parts):
  return " ".join(str(int(part)) for part in parts).encode("ascii")


def build_command(src_id, dst_id, *payload):
  return _encode((MSG_COMMAND, src_id, dst_id) + tuple(payload))


def build_status(src_id, dst_id, health_bitmap, *payload):
  return _encode((MSG_STATUS, src_id, dst_id, health_bitmap) + tuple(payload))


def parse_frame(msg):
  try:
    return [int(part) for part in msg.decode("ascii").split()]
  except Exception:
    return None
