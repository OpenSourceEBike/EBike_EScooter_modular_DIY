#############################################
#
# Choose the EBike/EScooter model on config.py:
from common.config_runtime import model, model_name, MODEL_FIIDO_Q1_S, MODEL_ESCOOTER_I12, MODEL_BAFANG_M500

print('EBike/EScooter model: ' + model_name)
print()

if model == MODEL_FIIDO_Q1_S:
    import escooter_fiido_q1_s.main
elif model == MODEL_ESCOOTER_I12:
    import escooter_fiido_q1_s.main # the same code as Fiido Q1S
elif model == MODEL_BAFANG_M500:
    import ebike_bafang_m500.main
else:
    raise 'You need to select a valid EBike/EScooter model'
