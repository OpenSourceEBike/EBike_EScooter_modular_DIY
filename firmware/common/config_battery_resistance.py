class BatteryResistanceConfig:
  """Motor-side measurement plus Display-side presentation/persistence config."""

  def __init__(self):
    # Motor-side passive estimator. Current units are A x100.
    self.boot_delay_ms = 180000
    self.reference_current_min_a_x100 = 200
    self.load_current_min_a_x100 = 1500
    self.min_current_step_a_x100 = 1000
    self.load_current_stability_a_x100 = 200

    self.load_qualify_ms = 5000
    self.sample_count = 3
    self.sample_min_interval_ms = 500
    self.sample_collection_timeout_ms = 5000
    self.reference_max_age_ms = 1000
    self.motor_sample_gap_ms = 1500

    # VESC STATUS_4 current and STATUS_5 voltage arrive independently.
    self.vesc_signal_max_age_ms = 1500
    self.vesc_voltage_current_max_skew_ms = 250
    self.dual_vesc_max_skew_ms = 250

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
    "boot_delay_ms",
    "reference_current_min_a_x100",
    "load_current_min_a_x100",
    "min_current_step_a_x100",
    "load_current_stability_a_x100",
    "load_qualify_ms",
    "sample_count",
    "sample_min_interval_ms",
    "sample_collection_timeout_ms",
    "reference_max_age_ms",
    "motor_sample_gap_ms",
    "vesc_signal_max_age_ms",
    "vesc_voltage_current_max_skew_ms",
    "dual_vesc_max_skew_ms",
    "min_mohm",
    "max_mohm",
  )
  error = _require_ints(config, names)
  if error is not None:
    return error

  if config.boot_delay_ms < 0:
    return "boot_delay_ms must be >= 0"
  if config.reference_current_min_a_x100 < 0:
    return "reference current must be >= 0"
  if config.load_current_min_a_x100 <= config.reference_current_min_a_x100:
    return "load current must exceed reference current"
  if config.min_current_step_a_x100 <= 0:
    return "min current step must be > 0"
  if config.load_current_stability_a_x100 < 0:
    return "load current stability must be >= 0"
  if config.load_qualify_ms <= 0:
    return "load_qualify_ms must be > 0"
  if config.sample_count != 3:
    return "sample_count must be 3"
  if config.sample_min_interval_ms <= 0:
    return "sample_min_interval_ms must be > 0"
  if config.sample_collection_timeout_ms < (
      (config.sample_count - 1) * config.sample_min_interval_ms):
    return "sample collection window is too short"
  if config.reference_max_age_ms <= 0:
    return "reference_max_age_ms must be > 0"
  if config.motor_sample_gap_ms < config.sample_min_interval_ms:
    return "motor sample gap must cover sample interval"
  if config.vesc_signal_max_age_ms <= 0:
    return "vesc_signal_max_age_ms must be > 0"
  if (config.vesc_voltage_current_max_skew_ms < 0 or
      config.vesc_voltage_current_max_skew_ms >
        config.vesc_signal_max_age_ms):
    return "invalid VESC voltage/current timestamp skew"
  if (config.dual_vesc_max_skew_ms < 0 or
      config.dual_vesc_max_skew_ms > config.vesc_signal_max_age_ms):
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
