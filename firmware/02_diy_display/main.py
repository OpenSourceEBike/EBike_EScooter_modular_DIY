#############################################
#
# Choose the EBike/EScooter type on common/espnow_commands.py:
import common.config_runtime as cfg
from common.model_constants import TYPE_EBIKE, TYPE_ESCOOTER

try:
  if hasattr(cfg, "pin_bl"):
    # Matches LCD default wiring: backlight_inverted=True means driving 0 turns it on.
    from machine import Pin
    Pin(cfg.pin_bl, Pin.OUT, value=0)
except Exception:
  pass

print('EBike/EScooter type: ' + cfg.type_name)
print()

vehicle_type = cfg.type.get("ebike_escooter")
if vehicle_type == TYPE_ESCOOTER:
  import escooter.main
elif vehicle_type == TYPE_EBIKE:
  import ebike.main
else:
  raise ValueError(
    "Selected config must define type['ebike_escooter'] as TYPE_EBIKE or TYPE_ESCOOTER"
  )
