#############################################
#
# Choose here which EBike/EScooter type firmware to run:
from common.config_runtime import type as cfg_type, type_name
from common.model_constants import TYPE_EBIKE, TYPE_ESCOOTER

print('EBike/EScooter type: ' + type_name)
print()

vehicle_type = cfg_type.get("ebike_escooter") if isinstance(cfg_type, dict) else None

if vehicle_type == TYPE_EBIKE:
  import ebike.main
elif vehicle_type == TYPE_ESCOOTER:
  import escooter.main
else:
  raise ValueError("You need to select a valid EBike/EScooter type")
