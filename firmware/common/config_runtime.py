# Centralized config loader.
# Deployment convention: exactly one config_*.py must be present at the
# device root at boot time. Keep extra configs in the source checkout, but
# copy only the target config to the board before flashing/booting.
# The loader exposes config values plus helper names.

import uos
import time
from common.model_constants import TYPE_EBIKE, TYPE_ESCOOTER

TYPE_NAME = {
  TYPE_EBIKE: "ebike",
  TYPE_ESCOOTER: "escooter",
}

_config_runtime_t0 = time.ticks_ms()
_discovery_done_ms = None
_import_done_ms = None


def _boot_log(label):
  if boot_timing_debug:
    elapsed_ms = time.ticks_diff(time.ticks_ms(), _config_runtime_t0)
    print("[config +{:>5} ms] {}".format(elapsed_ms, label))


def _list_root_configs():
  try:
    files = uos.listdir()
  except Exception:
    files = uos.listdir("/")
  return [f for f in files if f.startswith("config_") and f.endswith(".py")]


boot_timing_debug = False
_config_files = _list_root_configs()
_discovery_done_ms = time.ticks_ms()

if len(_config_files) != 1:
  if len(_config_files) > 1:
    print(
      "ERROR: multiple config_*.py files found at the root; boot aborted: {}".format(
        ", ".join(_config_files)
      )
    )
  raise ValueError(
    "Exactly one config_*.py must exist at the root; found: {}".format(
      ", ".join(_config_files) if _config_files else "none"
    )
  )

_config_module_name = _config_files[0][:-3]
_cfg = __import__(_config_module_name)
_import_done_ms = time.ticks_ms()
_cfg_obj = getattr(_cfg, "cfg", None)

# Merge cfg-object fields early so optional defaults cannot shadow them.
if _cfg_obj is not None:
  for _name in dir(_cfg_obj):
    if _name.startswith("_"):
      continue
    if not hasattr(_cfg, _name):
      setattr(_cfg, _name, getattr(_cfg_obj, _name))

# Optional display / lights / power settings used by the runtime boards.
_OPTIONAL_DEFAULTS = {
  "tail_always_enabled": False,
  "brake_tail_blink_enable": False,
  "brake_tail_on_ms": 400,
  "brake_tail_off_ms": 100,
  "bms_debug": False,
  "motion_detection_threshold": 16,
  "motion_detection_rate_hz": 25,
  "motion_detection_ac_mode": True,
  "timeout_no_motion_seconds_to_disable_relay": 300,
  "seconds_to_wait_before_movement_detection": 20,
  "boot_timing_debug": False,
  "espnow_debug": False,
  # Automatic lights schedule is optional; configs may ignore these values.
  "auto_lights_schedule_enabled": False,
  "auto_lights_schedule_enabled_at_boot_only": False,
  "auto_lights_on_hour": 19,
  "auto_lights_on_minute": 0,
  "auto_lights_off_hour": 7,
  "auto_lights_off_minute": 0,
}

for _name, _value in _OPTIONAL_DEFAULTS.items():
  if not hasattr(_cfg, _name):
    setattr(_cfg, _name, _value)


boot_timing_debug = _cfg.boot_timing_debug
if boot_timing_debug:
  print("[config +{:>5} ms] root config discovery complete".format(
    time.ticks_diff(_discovery_done_ms, _config_runtime_t0)))
  print("[config +{:>5} ms] selected config module imported: {}".format(
    time.ticks_diff(_import_done_ms, _config_runtime_t0), _config_module_name))
_boot_log("optional defaults applied")

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

_boot_log("module globals exported")

type_name = TYPE_NAME.get(vehicle_type, "unknown")

# Back-compat: attach MAC addresses to cfg object if present.
if _cfg_obj is not None:
  for _name in dir(_cfg):
    if _name.startswith("mac_address_"):
      setattr(_cfg_obj, _name, getattr(_cfg, _name))
  # Promote cfg object fields to module-level for consistency.
  for _name in dir(_cfg_obj):
    if not _name.startswith("_") and _name not in globals():
      globals()[_name] = getattr(_cfg_obj, _name)

_boot_log("cfg object merged")
