import os
import tempfile
import unittest
from unittest.mock import patch

import common.battery_resistance_persistence as persistence
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

  def test_partial_migration_never_replaces_existing_legacy_history(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path, 'w') as history:
        history.write(_LEGACY_HISTORY_HEADER)
        history.write('2026-09-18T12:00:00,34,5381,-130,5170,-6130\n')
        history.write('2026-09-18T12:01:00,36,5380,-131,5160,-6140\n')
      with open(config.history_file_path + '.migrate.tmp', 'w') as temporary:
        temporary.write(_HISTORY_HEADER)
        temporary.write('2026-09-18T12:00:00,34,na\n')

      state = _State(37)
      state.battery_resistance_history_dirty = False
      self.assertTrue(load_battery_resistance_history(state, config))
      self.assertEqual(state.battery_resistance_last_mohm, 36)
      self.assertFalse(state.battery_resistance_history_migration_repair_pending)
      self.assertTrue(save_battery_resistance_history(_State(37), config))
      with open(config.history_file_path) as history:
        contents = history.read()
      self.assertIn('2026-09-18T12:00:00,34,na\n', contents)
      self.assertIn('2026-09-18T12:01:00,36,na\n', contents)
      self.assertIn('na,37,2735\n', contents)

  def test_rotation_write_failure_keeps_existing_history(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      self.assertTrue(save_battery_resistance_history(_State(34), config))
      with open(config.history_file_path) as history:
        original = history.read()
      config.history_file_max_bytes = len(original) + 1
      real_open = open

      def fail_rotation_open(path, mode='r', *args, **kwargs):
        if path == config.history_file_path + '.rotate.tmp' and mode == 'w':
          raise OSError('simulated flash failure')
        return real_open(path, mode, *args, **kwargs)

      with patch('builtins.open', side_effect=fail_rotation_open):
        self.assertFalse(save_battery_resistance_history(_State(35), config))
      with open(config.history_file_path) as history:
        self.assertEqual(history.read(), original)

  def test_failed_rotation_publish_recovers_without_duplicate_on_retry(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      self.assertTrue(save_battery_resistance_history(_State(34), config))
      config.history_file_max_bytes = os.path.getsize(config.history_file_path) + 1
      state = _State(35)
      state.battery_resistance_pending_records = [(0, 35, 2735)]

      with patch.object(persistence._fs, 'rename', side_effect=OSError('reset')):
        self.assertFalse(save_battery_resistance_history(state, config))
      self.assertFalse(os.path.exists(config.history_file_path))
      self.assertTrue(save_battery_resistance_history(state, config))
      self.assertEqual(state.battery_resistance_pending_records, [])
      with open(config.history_file_path) as history:
        self.assertEqual(history.read(), _HISTORY_HEADER + 'na,35,2735\n')

  def test_recovered_rotation_does_not_drop_next_measurement(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path + '.rotate.tmp', 'w') as temporary:
        temporary.write(_HISTORY_HEADER + 'na,35,2735\n')
      state = _State(36)
      state.battery_resistance_pending_records = [(0, 36, 2800)]

      self.assertTrue(load_battery_resistance_history(_State(), config))
      self.assertTrue(save_battery_resistance_history(state, config))
      with open(config.history_file_path) as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + 'na,35,2735\n' + 'na,36,2800\n')

  def test_pending_measurements_are_not_coalesced(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State(36, 2800)
      state.battery_resistance_min_mohm = 34
      state.battery_resistance_pending_records = [
        (0, 34, 2600),
        (0, 36, 2800),
      ]

      self.assertTrue(save_battery_resistance_history(state, config))

      self.assertEqual(state.battery_resistance_pending_records, [])
      self.assertFalse(state.battery_resistance_history_dirty)
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER +
          'na,34,2600\n'
          'na,36,2800\n')

  def test_failed_pending_append_remains_queued_for_retry(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State()
      state.battery_resistance_pending_records = [(0, 999, 2735)]

      self.assertFalse(save_battery_resistance_history(state, config))
      self.assertEqual(
        state.battery_resistance_pending_records, [(0, 999, 2735)])
      self.assertTrue(state.battery_resistance_history_dirty)

  def test_summary_retry_does_not_duplicate_an_appended_pending_row(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State()
      state.battery_resistance_pending_records = [(0, 35, 2735)]

      with patch.object(
          persistence, '_save_summary_atomic', return_value=False):
        self.assertFalse(save_battery_resistance_history(state, config))

      self.assertEqual(state.battery_resistance_pending_records, [])
      self.assertTrue(state.battery_resistance_history_dirty)
      self.assertTrue(save_battery_resistance_history(state, config))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + 'na,35,2735\n')


if __name__ == '__main__':
  unittest.main()
