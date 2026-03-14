# Centralized config loader. Loads the single config_*.py at the root
# and exposes config values plus helper names.

import uos
from common.model_constants import TYPE_EBIKE, TYPE_ESCOOTER

TYPE_NAME = {
  TYPE_EBIKE: "ebike",
  TYPE_ESCOOTER: "escooter",
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

# Optional lights settings used by 03_diy_lights_board.
_OPTIONAL_DEFAULTS = {
  "tail_always_enabled": False,
  "brake_tail_blink_enable": False,
  "brake_tail_on_ms": 400,
  "brake_tail_off_ms": 100,
}

for _name, _value in _OPTIONAL_DEFAULTS.items():
  if not hasattr(_cfg, _name):
    setattr(_cfg, _name, _value)

type = getattr(_cfg, "type", None)
if not isinstance(type, dict):
  raise ValueError("Selected config must define 'type' as a dict")

vehicle_type = type.get("ebike_escooter")
if vehicle_type not in TYPE_NAME:
  raise ValueError(
    "Selected config must define type['ebike_escooter'] as TYPE_EBIKE or TYPE_ESCOOTER"
  )

# Re-export all config values
for _name in dir(_cfg):
  if not _name.startswith("_"):
    globals()[_name] = getattr(_cfg, _name)

type_name = TYPE_NAME.get(vehicle_type, "unknown")

# Back-compat: attach MAC addresses to cfg object if present.
if "cfg" in globals():
  _cfg_obj = globals()["cfg"]
  for _name in dir(_cfg):
    if _name.startswith("mac_address_"):
      setattr(_cfg_obj, _name, getattr(_cfg, _name))
  # Promote cfg object fields to module-level for consistency.
  for _name in dir(_cfg_obj):
    if not _name.startswith("_") and _name not in globals():
      globals()[_name] = getattr(_cfg_obj, _name)
