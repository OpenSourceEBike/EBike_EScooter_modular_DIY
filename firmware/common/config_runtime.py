# Centralized config loader. Reads model from config.py and exposes
# model-specific overrides plus helper names.

import config as _base

MODEL_ESCOOTER_DUAL_MOTOR = _base.MODEL_ESCOOTER_DUAL_MOTOR
MODEL_ESCOOTER_SINGLE_MOTOR = _base.MODEL_ESCOOTER_SINGLE_MOTOR
MODEL_EBIKE = _base.MODEL_EBIKE

model = _base.model

MODEL_NAME = {
  MODEL_ESCOOTER_DUAL_MOTOR: "escooter_dual_motor",
  MODEL_ESCOOTER_SINGLE_MOTOR: "escooter_single_motor",
  MODEL_EBIKE: "ebike",
}

if model == MODEL_ESCOOTER_DUAL_MOTOR:
  from config_escooter_fiido_q1_s import *
elif model == MODEL_ESCOOTER_SINGLE_MOTOR:
  from config_escooter_iscooter_i12 import *
elif model == MODEL_EBIKE:
  from config_ebike_bafang_m500 import *
else:
  raise ValueError("You need to select a valid EBike/EScooter model")

model_name = MODEL_NAME.get(model, "unknown")
