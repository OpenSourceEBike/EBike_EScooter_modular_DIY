import os
import tempfile
import unittest

from common.battery_resistance_persistence import (
  _LEGACY_HISTORY_HEADER,
  _HISTORY_HEADER,
  load_battery_resistance_history,
  save_battery_resistance_history,
)
from common.config_bms_battery_resistance import BmsBatteryResistanceConfig


class _State:
  def __init__(self, resistance_mohm=35, temperature_c_x100=2735):
    self.battery_resistance_last_mohm = resistance_mohm
    self.battery_resistance_last_timestamp = 0
    self.battery_resistance_last_bms_temperature_c_x100 = temperature_c_x100
    self.battery_resistance_min_mohm = resistance_mohm
    self.battery_resistance_min_timestamp = 0
    self.battery_resistance_max_mohm = resistance_mohm
    self.battery_resistance_max_timestamp = 0
    self.battery_resistance_history_dirty = True
    self.battery_resistance_history_row_saved = False
    self.battery_resistance_summary_repair_pending = False


class BmsBatteryResistancePersistenceTests(unittest.TestCase):
  def _config(self, directory):
    config = BmsBatteryResistanceConfig()
    config.history_file_path = os.path.join(directory, 'history.csv')
    config.summary_file_path = os.path.join(directory, 'summary.csv')
    return config

  def test_history_stores_only_timestamp_resistance_and_bms_temperature(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      self.assertTrue(save_battery_resistance_history(_State(), config))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          'timestamp,resistance_mohm,bms_temperature_c_x100\n'
          'na,35,2735\n')

  def test_legacy_history_is_preserved_with_unknown_temperature(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path, 'w') as history:
        history.write(_LEGACY_HISTORY_HEADER)
        history.write('2026-09-18T12:00:00,34,5381,-130,5170,-6130\n')

      self.assertTrue(save_battery_resistance_history(_State(35, 2735), config))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER +
          '2026-09-18T12:00:00,34,na\n'
          'na,35,2735\n')

  def test_migration_temporary_generation_is_recovered_after_reset(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      temporary_path = config.history_file_path + '.migrate.tmp'
      with open(temporary_path, 'w') as history:
        history.write(_HISTORY_HEADER)
        history.write('2026-09-18T12:00:00,34,na\n')

      state = _State()
      state.battery_resistance_history_dirty = False
      self.assertTrue(load_battery_resistance_history(state, config))
      self.assertTrue(state.battery_resistance_history_migration_repair_pending)
      self.assertTrue(save_battery_resistance_history(state, config))

      self.assertFalse(os.path.exists(temporary_path))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + '2026-09-18T12:00:00,34,na\n')


if __name__ == '__main__':
  unittest.main()
