#############################################
#
# Choose the EBike/EScooter model on common/espnow_commands.py:
from common.config_runtime import (
  model,
  model_name,
  MODEL_ESCOOTER_DUAL_MOTOR,
  MODEL_ESCOOTER_SINGLE_MOTOR,
  MODEL_EBIKE,
)

print('EBike/EScooter model: ' + model_name)
print()

if model in (MODEL_ESCOOTER_DUAL_MOTOR, MODEL_ESCOOTER_SINGLE_MOTOR):
  import escooter.main
elif model == MODEL_EBIKE:
  import ebike.main
else:
  raise ValueError("You need to select a valid EBike/EScooter model")
