# Centralized config loader. Reads model from config.py and exposes
# model-specific overrides plus helper names.

import config as _base

MODEL_FIIDO_Q1_S = _base.MODEL_FIIDO_Q1_S
MODEL_ESCOOTER_I12 = _base.MODEL_ESCOOTER_I12
MODEL_BAFANG_M500 = _base.MODEL_BAFANG_M500

model = _base.model

MODEL_NAME = {
    MODEL_FIIDO_Q1_S: "escooter_fiido_q1_s",
    MODEL_ESCOOTER_I12: "escooter_iscooter_i12",
    MODEL_BAFANG_M500: "ebike_bafang_m500",
}

if model == MODEL_FIIDO_Q1_S:
    from config_escooter_fiido_q1_s import *  # noqa: F401,F403
elif model == MODEL_ESCOOTER_I12:
    from config_escooter_iscooter_i12 import *  # noqa: F401,F403
elif model == MODEL_BAFANG_M500:
    from config_ebike_bafang_m500 import *  # noqa: F401,F403
else:
    raise ValueError("You need to select a valid EBike/EScooter model")

model_name = MODEL_NAME.get(model, "unknown")
