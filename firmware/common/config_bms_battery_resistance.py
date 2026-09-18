class BmsBatteryResistanceConfig:
  """Display-only configuration for the passive JBD BASIC estimator."""

  def __init__(self):
    self.min_mohm = 1
    self.max_mohm = 500
    self.min_voltage_drop_x100 = 10
    self.reference_power_min_w = -250
    self.reference_power_max_w = 250
    self.load_power_min_w = 750
    self.baseline_sample_count = 3
    self.load_sample_count = 3
    self.load_event_max_ms = 15000
    self.buffer_size = 16
    self.history_file_path = "bms_battery_resistance_history.csv"
    self.summary_file_path = "bms_battery_resistance_summary.csv"
    self.history_file_max_bytes = 100 * 1024
    self.alert_duration_ms = 5000


bms_battery_resistance_config = BmsBatteryResistanceConfig()


def validate_bms_battery_resistance_config(config):
  try:
    values = (
      config.min_mohm, config.max_mohm, config.min_voltage_drop_x100,
      config.reference_power_min_w, config.reference_power_max_w,
      config.load_power_min_w, config.baseline_sample_count,
      config.load_sample_count, config.load_event_max_ms, config.buffer_size,
      config.history_file_max_bytes, config.alert_duration_ms,
    )
    paths = (config.history_file_path, config.summary_file_path)
  except AttributeError:
    return "missing BMS resistance setting"
  if any(not isinstance(value, int) or isinstance(value, bool)
         for value in values):
    return "BMS resistance settings must be integers"
  if (config.min_mohm <= 0 or config.max_mohm <= config.min_mohm or
      config.min_voltage_drop_x100 <= 0 or
      config.reference_power_min_w >= config.reference_power_max_w or
      config.reference_power_min_w != -250 or
      config.reference_power_max_w != 250 or
      config.load_power_min_w != 750 or
      config.baseline_sample_count < 2 or config.load_sample_count < 2 or
      config.load_event_max_ms < 1000 or config.load_event_max_ms > 120000 or
      config.buffer_size < max(config.baseline_sample_count,
                               config.load_sample_count) or
      config.history_file_max_bytes < 256 or config.alert_duration_ms <= 0):
    return "invalid BMS resistance setting"
  if (any(not isinstance(path, str) or not path for path in paths) or
      paths[0] == paths[1] or paths[0] == paths[1] + '.tmp'):
    return "invalid BMS resistance history path"
  return None
