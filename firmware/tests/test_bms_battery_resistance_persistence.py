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

  def test_history_stores_named_measurement_fields(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      self.assertTrue(save_battery_resistance_history(_State(), config))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + 'na,35,na,na,na,na,na,na,2735,na,na\n')

  def test_history_persists_exact_estimator_metadata_and_load_range(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State()
      state.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 147,
        'before_voltage_x100': 5200, 'before_current_x100': -100,
        'after_voltage_x100': 4906, 'after_current_x100': -2100,
        'delta_voltage_x100': 294, 'delta_current_x100': 2000,
        'bms_temperature_c_x100': 2450,
        'load_current_min_x100': -2140,
        'load_current_max_x100': -2060,
      }]
      self.assertTrue(save_battery_resistance_history(state, config))
      with open(config.history_file_path) as history:
        lines = history.readlines()
      self.assertEqual(lines[0], _HISTORY_HEADER)
      self.assertEqual(lines[1].strip().split(',')[1:], [
        '147', '5200', '-100', '4906', '-2100', '294', '2000',
        '2450', '-2140', '-2060'])

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
          '2026-09-18T12:00:00,34,5381,-130,5170,-6130,na,na,na,na,na\n'
          'na,35,na,na,na,na,na,na,2735,na,na\n')

  def test_simplified_history_migrates_and_keeps_temperature(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path, 'w') as history:
        history.write('timestamp,resistance_mohm,bms_temperature_c_x100\n')
        history.write('2026-09-18T12:00:00,34,2510\n')
      self.assertTrue(save_battery_resistance_history(_State(35), config))
      with open(config.history_file_path) as history:
        rows = history.readlines()
      self.assertEqual(rows[0], _HISTORY_HEADER)
      self.assertEqual(
        rows[1],
        '2026-09-18T12:00:00,34,na,na,na,na,na,na,2510,na,na\n')

  def test_reboot_repairs_summary_from_new_history_then_appends(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      first = _State(35, 2735)
      first.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 35,
        'before_voltage_x100': 5381, 'before_current_x100': -130,
        'after_voltage_x100': 5170, 'after_current_x100': -6130,
        'delta_voltage_x100': 211, 'delta_current_x100': 6000,
        'bms_temperature_c_x100': 2735,
        'load_current_min_x100': -6130,
        'load_current_max_x100': -6130,
      }]
      self.assertTrue(save_battery_resistance_history(first, config))
      os.remove(config.summary_file_path)

      rebooted = _State()
      rebooted.battery_resistance_history_dirty = False
      self.assertTrue(load_battery_resistance_history(rebooted, config))
      self.assertEqual(rebooted.battery_resistance_last_mohm, 35)
      self.assertTrue(rebooted.battery_resistance_summary_repair_pending)
      self.assertTrue(save_battery_resistance_history(rebooted, config))

      rebooted.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 36,
        'bms_temperature_c_x100': None,
      }]
      rebooted.battery_resistance_last_mohm = 36
      rebooted.battery_resistance_max_mohm = 36
      rebooted.battery_resistance_history_dirty = True
      self.assertTrue(save_battery_resistance_history(rebooted, config))
      with open(config.history_file_path) as history:
        rows = history.readlines()
      self.assertEqual(len(rows), 3)
      self.assertEqual(rows[1].split(',')[1:8], [
        '35', '5381', '-130', '5170', '-6130', '211', '6000'])
      self.assertEqual(rows[2].split(',')[1], '36')

  def test_missing_temperature_is_persisted_as_na(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      self.assertTrue(save_battery_resistance_history(
        _State(35, None), config))
      with open(config.history_file_path) as history:
        self.assertTrue(history.readlines()[1].endswith(',na,na,na\n'))

  def test_migration_temporary_generation_is_recovered_after_reset(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      temporary_path = config.history_file_path + '.migrate.tmp'
      with open(temporary_path, 'w') as history:
        history.write(_HISTORY_HEADER)
        history.write(
          '2026-09-18T12:00:00,34,na,na,na,na,na,na,na,na,na\n')

      state = _State()
      state.battery_resistance_history_dirty = False
      self.assertTrue(load_battery_resistance_history(state, config))
      self.assertTrue(state.battery_resistance_history_migration_repair_pending)
      self.assertTrue(save_battery_resistance_history(state, config))

      self.assertFalse(os.path.exists(temporary_path))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER +
          '2026-09-18T12:00:00,34,na,na,na,na,na,na,na,na,na\n')

  def test_partial_migration_never_replaces_existing_legacy_history(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path, 'w') as history:
        history.write(_LEGACY_HISTORY_HEADER)
        history.write('2026-09-18T12:00:00,34,5381,-130,5170,-6130\n')
        history.write('2026-09-18T12:01:00,36,5380,-131,5160,-6140\n')
      with open(config.history_file_path + '.migrate.tmp', 'w') as temporary:
        temporary.write(_HISTORY_HEADER)
        temporary.write(
          '2026-09-18T12:00:00,34,na,na,na,na,na,na,na,na,na\n')

      state = _State(37)
      state.battery_resistance_history_dirty = False
      self.assertTrue(load_battery_resistance_history(state, config))
      self.assertEqual(state.battery_resistance_last_mohm, 36)
      self.assertFalse(state.battery_resistance_history_migration_repair_pending)
      self.assertTrue(save_battery_resistance_history(_State(37), config))
      with open(config.history_file_path) as history:
        contents = history.read()
      self.assertIn(
        '2026-09-18T12:00:00,34,5381,-130,5170,-6130,na,na,na,na,na\n',
        contents)
      self.assertIn(
        '2026-09-18T12:01:00,36,5380,-131,5160,-6140,na,na,na,na,na\n',
        contents)
      self.assertIn('na,37,na,na,na,na,na,na,2735,na,na\n', contents)

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
      state.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 35,
        'bms_temperature_c_x100': 2735,
      }]

      with patch.object(persistence._fs, 'rename', side_effect=OSError('reset')):
        self.assertFalse(save_battery_resistance_history(state, config))
      self.assertFalse(os.path.exists(config.history_file_path))
      self.assertTrue(save_battery_resistance_history(state, config))
      self.assertEqual(state.battery_resistance_pending_records, [])
      with open(config.history_file_path) as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + 'na,35,na,na,na,na,na,na,2735,na,na\n')

  def test_recovered_rotation_does_not_drop_next_measurement(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      with open(config.history_file_path + '.rotate.tmp', 'w') as temporary:
        temporary.write(
          _HISTORY_HEADER + 'na,35,na,na,na,na,na,na,2735,na,na\n')
      state = _State(36)
      state.battery_resistance_pending_records = [(0, 36, 2800)]

      self.assertTrue(load_battery_resistance_history(_State(), config))
      self.assertTrue(save_battery_resistance_history(state, config))
      with open(config.history_file_path) as history:
        self.assertEqual(
        history.read(),
          _HISTORY_HEADER +
          'na,35,na,na,na,na,na,na,2735,na,na\n' +
          'na,36,na,na,na,na,na,na,2800,na,na\n')

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
          'na,34,na,na,na,na,na,na,2600,na,na\n'
          'na,36,na,na,na,na,na,na,2800,na,na\n')

  def test_failed_pending_append_remains_queued_for_retry(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State()
      state.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 999,
        'bms_temperature_c_x100': 2735,
      }]

      self.assertFalse(save_battery_resistance_history(state, config))
      self.assertEqual(
        state.battery_resistance_pending_records,
        [{'timestamp': 0, 'resistance_mohm': 999,
          'bms_temperature_c_x100': 2735}])
      self.assertTrue(state.battery_resistance_history_dirty)

  def test_summary_retry_does_not_duplicate_an_appended_pending_row(self):
    with tempfile.TemporaryDirectory() as directory:
      config = self._config(directory)
      state = _State()
      state.battery_resistance_pending_records = [{
        'timestamp': 0, 'resistance_mohm': 35,
        'bms_temperature_c_x100': 2735,
      }]

      with patch.object(
          persistence, '_save_summary_atomic', return_value=False):
        self.assertFalse(save_battery_resistance_history(state, config))

      self.assertEqual(state.battery_resistance_pending_records, [])
      self.assertTrue(state.battery_resistance_history_dirty)
      self.assertTrue(save_battery_resistance_history(state, config))
      with open(config.history_file_path, 'r') as history:
        self.assertEqual(
          history.read(),
          _HISTORY_HEADER + 'na,35,na,na,na,na,na,na,2735,na,na\n')


if __name__ == '__main__':
  unittest.main()
