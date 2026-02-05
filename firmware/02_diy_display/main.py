#############################################
#
# Choose the EBike/EScooter type on common/espnow_commands.py:
from common.config_runtime import type_name, type as cfg_type
from common.model_constants import TYPE_EBIKE, TYPE_ESCOOTER

print('EBike/EScooter type: ' + type_name)
print()

vehicle_type = cfg_type.get("ebike_escooter")
if vehicle_type == TYPE_ESCOOTER:
  import escooter.main
elif vehicle_type == TYPE_EBIKE:
  import ebike.main
else:
  raise ValueError(
    "Selected config must define type['ebike_escooter'] as TYPE_EBIKE or TYPE_ESCOOTER"
  )
