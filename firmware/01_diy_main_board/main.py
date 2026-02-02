#############################################
#
# Choose here which EBike/EScooter model firmware to run:
from common.config_runtime import model, model_name, MODEL_EBIKE

print('EBike/EScooter model: ' + model_name)
print()

if model == MODEL_EBIKE:
  import ebike.main
else:
  import escooter.main
