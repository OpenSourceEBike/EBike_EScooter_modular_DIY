#############################################
#
# Choose here which EBike/EScooter model firmware to run:
from common.config_runtime import model, model_name, MODEL_FIIDO_Q1_S, MODEL_ESCOOTER_I12, MODEL_BAFANG_M500

print('EBike/EScooter model: ' + model_name)
print()

if model == MODEL_FIIDO_Q1_S:
    import escooter_fiido_q1_s.main
elif model == MODEL_ESCOOTER_I12:
    import escooter_iscooter_i12.main
elif model == MODEL_BAFANG_M500:
    import ebike_bafang_m500.main
else:
    raise 'You need to select a valid EBike/EScooter model'
