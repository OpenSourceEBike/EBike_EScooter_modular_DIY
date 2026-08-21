class BatteryResistanceConfig:
  """Motor-side measurement plus Display-side presentation/persistence config."""

  def __init__(self):
    # Motor-side passive estimator thresholds use W and ms; result uses mOhm.
    # Before an attempt, accumulate 60 distinct seconds with at least 200 W.
    # Samples in the same second count only once and need not be consecutive.
    self.boot_qualifying_power_min_w = 200
    self.boot_qualifying_seconds = 60
    self.reference_power_max_w = 200
    self.reference_qualify_ms = 15000
    self.load_power_min_w = 750

    self.load_qualify_ms = 10000
    self.sample_count = 3
    self.sample_min_interval_ms = 500
    self.sample_collection_timeout_ms = 5000

    # Project-private command 101 carries an atomic mV/mA sample per VESC.
    self.vesc_precision_sample_max_age_ms = 1500
    self.dual_vesc_precision_max_skew_ms = 250

    self.min_mohm = 1
    self.max_mohm = 2500

    # Display-side files, written only during explicit Display shutdown.
    self.history_file_path = "battery_resistance_history.csv"
    self.summary_file_path = "battery_resistance_summary.csv"
    self.history_file_max_bytes = 100 * 1024
    self.alert_duration_ms = 5000


battery_resistance_config = BatteryResistanceConfig()


def _is_plain_int(value):
  return isinstance(value, int) and not isinstance(value, bool)


def _require_ints(config, names):
  try:
    for name in names:
      if not _is_plain_int(getattr(config, name)):
        return "{} must be an integer".format(name)
  except AttributeError:
    return "missing measurement value"
  return None


def validate_battery_resistance_measurement_config(config):
  """Validate only settings owned by the motor-side estimator."""
  names = (
    "boot_qualifying_power_min_w",
    "boot_qualifying_seconds",
    "reference_power_max_w",
    "reference_qualify_ms",
    "load_power_min_w",
    "load_qualify_ms",
    "sample_count",
    "sample_min_interval_ms",
    "sample_collection_timeout_ms",
    "vesc_precision_sample_max_age_ms",
    "dual_vesc_precision_max_skew_ms",
    "min_mohm",
    "max_mohm",
  )
  error = _require_ints(config, names)
  if error is not None:
    return error

  if config.boot_qualifying_power_min_w < 0:
    return "boot qualifying power must be >= 0"
  if config.boot_qualifying_seconds < 0:
    return "boot_qualifying_seconds must be >= 0"
  if config.reference_power_max_w < 0:
    return "reference power must be >= 0"
  if config.reference_qualify_ms <= 0:
    return "reference_qualify_ms must be > 0"
  if config.load_power_min_w <= 0:
    return "load power must be > 0"
  if config.reference_power_max_w >= config.load_power_min_w:
    return "reference power must be below load power"
  if config.load_qualify_ms <= 0:
    return "load_qualify_ms must be > 0"
  if config.sample_count != 3:
    return "sample_count must be 3"
  if config.sample_min_interval_ms <= 0:
    return "sample_min_interval_ms must be > 0"
  if config.sample_collection_timeout_ms < (
      (config.sample_count - 1) * config.sample_min_interval_ms):
    return "sample collection window is too short"
  if config.vesc_precision_sample_max_age_ms <= 0:
    return "vesc_precision_sample_max_age_ms must be > 0"
  if (config.dual_vesc_precision_max_skew_ms < 0 or
      config.dual_vesc_precision_max_skew_ms >
        config.vesc_precision_sample_max_age_ms):
    return "invalid dual-VESC timestamp skew"
  if config.min_mohm <= 0 or config.max_mohm <= config.min_mohm:
    return "invalid resistance range"
  return None


def validate_battery_resistance_display_config(config):
  """Validate only settings owned by Display UI and file persistence."""
  error = _require_ints(config, (
    "min_mohm", "max_mohm", "history_file_max_bytes", "alert_duration_ms"
  ))
  if error is not None:
    return error
  if config.min_mohm <= 0 or config.max_mohm <= config.min_mohm:
    return "invalid resistance range"
  try:
    history_path = config.history_file_path
    summary_path = config.summary_file_path
  except AttributeError:
    return "missing history file setting"
  if (not isinstance(history_path, str) or
      not isinstance(summary_path, str) or
      not history_path or not summary_path or
      config.history_file_max_bytes < 256):
    return "invalid history file settings"
  if history_path == summary_path:
    return "history and summary paths must differ"
  if history_path == summary_path + ".tmp":
    return "history path collides with summary temp path"
  if config.alert_duration_ms <= 0:
    return "alert_duration_ms must be > 0"
  return None


def validate_battery_resistance_config(config):
  """Compatibility validator covering both board-owned config subsets."""
  error = validate_battery_resistance_measurement_config(config)
  if error is not None:
    return error
  return validate_battery_resistance_display_config(config)
