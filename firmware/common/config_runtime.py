# Centralized config loader. Loads the single config_*.py at the root
# and exposes model-specific overrides plus helper names.

import uos
from common.model_constants import (
  MODEL_ESCOOTER_DUAL_MOTOR,
  MODEL_ESCOOTER_SINGLE_MOTOR,
  MODEL_EBIKE,
)

MODEL_NAME = {
  MODEL_ESCOOTER_DUAL_MOTOR: "escooter_dual_motor",
  MODEL_ESCOOTER_SINGLE_MOTOR: "escooter_single_motor",
  MODEL_EBIKE: "ebike",
}


def _list_root_configs():
  try:
    files = uos.listdir()
  except Exception:
    files = uos.listdir("/")
  return [f for f in files if f.startswith("config_") and f.endswith(".py")]


_config_files = _list_root_configs()

if len(_config_files) != 1:
  raise ValueError(
    "Exactly one config_*.py must exist at the root; found: {}".format(
      ", ".join(_config_files) if _config_files else "none"
    )
  )

_config_module_name = _config_files[0][:-3]
_cfg = __import__(_config_module_name)

model = getattr(_cfg, "model", None)
if model is None:
  raise ValueError("Selected config must define 'model' (e.g. MODEL_ESCOOTER_SINGLE_MOTOR)")

# Re-export all config values
for _name in dir(_cfg):
  if not _name.startswith("_"):
    globals()[_name] = getattr(_cfg, _name)

model_name = MODEL_NAME.get(model, "unknown")

# Back-compat: attach MAC addresses to cfg object if present.
if "cfg" in globals():
  _cfg_obj = globals()["cfg"]
  for _name in dir(_cfg):
    if _name.startswith("mac_address_"):
      setattr(_cfg_obj, _name, getattr(_cfg, _name))
