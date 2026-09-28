import time

try:
  import uos as _fs
except ImportError:
  import os as _fs


_SUMMARY_HEADER = 'kind,resistance_mohm,timestamp'
_HISTORY_HEADER = (
  'timestamp,resistance_mohm,before_voltage_x100,before_current_x100,'
  'after_voltage_x100,after_current_x100,delta_voltage_x100,'
  'delta_current_x100,bms_temperature_c_x100,load_current_min_x100,'
  'load_current_max_x100\n')
_SIMPLIFIED_HISTORY_HEADER = 'timestamp,resistance_mohm,bms_temperature_c_x100\n'
_LEGACY_HISTORY_HEADER = (
  'timestamp,resistance_mohm,before_voltage_x100,before_current_x100,'
  'after_voltage_x100,after_current_x100\n')


def _timestamp_from_csv(value):
  if not value or value == 'na':
    return 0
  try:
    date_part, time_part = value.split('T')
    year, month, day = (int(part) for part in date_part.split('-'))
    hour, minute, second = (int(part) for part in time_part.split(':'))
    return time.mktime((year, month, day, hour, minute, second, 0, 0))
  except (TypeError, ValueError, OverflowError, OSError):
    return 0


def _timestamp_to_csv(timestamp):
  if not timestamp:
    return 'na'
  try:
    dt = time.localtime(timestamp)
    return "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}".format(
      dt[0], dt[1], dt[2], dt[3], dt[4], dt[5]
    )
  except Exception:
    return 'na'


def _valid_value(config, value):
  return config.min_mohm <= value <= config.max_mohm


def _read_summary(path, config):
  loaded = {}
  try:
    with open(path, 'r') as summary:
      if summary.readline().strip() != _SUMMARY_HEADER:
        return None
      for line in summary:
        parts = line.strip().split(',')
        if len(parts) != 3:
          continue
        kind, value, timestamp = parts
        try:
          resistance_mohm = int(value)
        except ValueError:
          continue
        if (not _valid_value(config, resistance_mohm) or
            kind not in ('last', 'min', 'max') or kind in loaded):
          return None
        loaded[kind] = (
          resistance_mohm,
          _timestamp_from_csv(timestamp),
        )
  except OSError:
    return None

  if not all(kind in loaded for kind in ('last', 'min', 'max')):
    return None
  if not loaded['min'][0] <= loaded['last'][0] <= loaded['max'][0]:
    return None
  return loaded


def _read_history(path, config):
  """Read at most the configured 100 KiB and return its aggregate state."""
  result = None
  try:
    with open(path, 'r') as history:
      header = history.readline()
      if header == _HISTORY_HEADER:
        field_count = 11
      elif header == _SIMPLIFIED_HISTORY_HEADER:
        field_count = 3
      elif header == _LEGACY_HISTORY_HEADER:
        field_count = 6
      else:
        return None
      for line in history:
        # A reset during append may leave a syntactically plausible prefix
        # (for example "...,8" instead of "...,83"). Only newline-terminated
        # records are committed records.
        if not line.endswith('\n'):
          continue
        parts = line.strip().split(',')
        if len(parts) != field_count:
          continue
        timestamp, value = parts[0], parts[1]
        try:
          resistance_mohm = int(value)
        except ValueError:
          continue
        if not _valid_value(config, resistance_mohm):
          continue
        item = (resistance_mohm, _timestamp_from_csv(timestamp))
        if result is None:
          result = {'last': item, 'min': item, 'max': item}
        else:
          result['last'] = item
          if resistance_mohm < result['min'][0]:
            result['min'] = item
          if resistance_mohm > result['max'][0]:
            result['max'] = item
  except OSError:
    return None
  return result


def _merge_summary_and_history(summary, history):
  if summary is None:
    return history
  if history is None:
    return summary

  merged = dict(summary)
  # History is committed before summary. Its final complete row is therefore
  # authoritative if power disappeared between the two writes.
  merged['last'] = history['last']
  if history['min'][0] < merged['min'][0]:
    merged['min'] = history['min']
  if history['max'][0] > merged['max'][0]:
    merged['max'] = history['max']
  return merged


def _apply_summary(state, summary):
  state.battery_resistance_last_mohm = summary['last'][0]
  state.battery_resistance_last_timestamp = summary['last'][1]
  state.battery_resistance_last_bms_temperature_c_x100 = None
  state.battery_resistance_min_mohm = summary['min'][0]
  state.battery_resistance_min_timestamp = summary['min'][1]
  state.battery_resistance_max_mohm = summary['max'][0]
  state.battery_resistance_max_timestamp = summary['max'][1]
  state.battery_resistance_measurement = {}


def load_battery_resistance_history(state, config):
  """Load and reconcile recoverable summary generations with history."""
  _recover_rotated_history(config.history_file_path, config)
  path = config.summary_file_path
  candidates = (
    (path + '.tmp', _read_summary(path + '.tmp', config)),
    (path, _read_summary(path, config)),
  )
  summary_path = None
  summary = None
  for candidate_path, candidate in candidates:
    if candidate is not None:
      summary_path = candidate_path
      summary = candidate
      break

  history_path = None
  history = None
  # A migration temporary may contain only a prefix if power failed during
  # its write. The original is authoritative until it has been removed.
  history_candidates = (config.history_file_path,)
  if _file_size(config.history_file_path) == 0:
    history_candidates += (config.history_file_path + '.migrate.tmp',)
  for candidate_path in history_candidates:
    candidate = _read_history(candidate_path, config)
    if candidate is not None:
      history_path = candidate_path
      history = candidate
      break
  merged = _merge_summary_and_history(summary, history)
  if merged is None:
    return False

  _apply_summary(state, merged)
  state.battery_resistance_summary_repair_pending = (
    summary_path != path or merged != summary
  )
  state.battery_resistance_history_migration_repair_pending = (
    history_path == config.history_file_path + '.migrate.tmp'
  )
  return True


def _file_size(path):
  try:
    return _fs.stat(path)[6]
  except OSError as ex:
    if ex.args and ex.args[0] == 2:
      return 0
    return None


def _remove_if_present(path):
  try:
    _fs.remove(path)
  except OSError as ex:
    return bool(ex.args and ex.args[0] == 2)
  return True


def _history_tail_is_complete(path, current_size):
  if current_size == 0:
    return True
  try:
    with open(path, 'rb') as history:
      history.seek(current_size - 1)
      return history.read(1) == b'\n'
  except (OSError, ValueError):
    return False


def _migrate_legacy_history(path, config):
  """Upgrade supported older CSV formats without dropping valid results."""
  current_size = _file_size(path)
  if current_size is None:
    return False
  if current_size == 0:
    return True
  try:
    with open(path, 'r') as history:
      header = history.readline()
      if header == _HISTORY_HEADER:
        return True
      if header not in (_LEGACY_HISTORY_HEADER,
                        _SIMPLIFIED_HISTORY_HEADER):
        return False
      legacy_field_count = (6 if header == _LEGACY_HISTORY_HEADER else 3)
      rows = []
      for line in history:
        if not line.endswith('\n'):
          continue
        parts = line.strip().split(',')
        if len(parts) != legacy_field_count:
          continue
        try:
          resistance_mohm = int(parts[1])
        except ValueError:
          continue
        if _valid_value(config, resistance_mohm):
          if legacy_field_count == 6:
            values = (parts[2], parts[3], parts[4], parts[5],
                      'na', 'na', 'na', 'na', 'na')
          else:
            values = ('na',) * 6 + (parts[2], 'na', 'na')
          rows.append((parts[0], resistance_mohm) + values)
  except (OSError, ValueError):
    return False

  temporary_path = path + '.migrate.tmp'
  try:
    with open(temporary_path, 'w') as migrated:
      migrated.write(_HISTORY_HEADER)
      for row in rows:
        migrated.write(','.join(str(value) for value in row) + '\n')
  except OSError:
    return False
  if not _remove_if_present(path):
    return False
  try:
    _fs.rename(temporary_path, path)
  except OSError:
    return False
  return True


def _recover_migrated_history(path, config):
  """Publish a migration only after its original has been removed."""
  temporary_path = path + '.migrate.tmp'
  if _file_size(path) != 0:
    return True
  if _read_history(temporary_path, config) is None:
    return True
  try:
    _fs.rename(temporary_path, path)
  except OSError:
    return False
  return True


def _recover_rotated_history(path, config):
  """Finish a rotation interrupted after removal of the old generation."""
  temporary_path = path + '.rotate.tmp'
  if _file_size(path) != 0:
    return None
  try:
    with open(temporary_path, 'r') as history:
      header = history.readline()
      row = history.readline()
      parts = row.strip().split(',')
      valid = (header == _HISTORY_HEADER and row.endswith('\n') and
               len(parts) == 11 and
               _valid_value(config, int(parts[1])) and
               history.readline() == '')
  except (OSError, ValueError, IndexError):
    return None
  if not valid:
    return None
  try:
    _fs.rename(temporary_path, path)
  except OSError:
    return None
  return row


def _append_history_record(record, config):
  try:
    if isinstance(record, dict):
      values = dict(record)
    else:
      timestamp, resistance_mohm, temperature_c_x100 = record
      values = {
        'timestamp': timestamp,
        'resistance_mohm': resistance_mohm,
        'bms_temperature_c_x100': temperature_c_x100,
      }
    timestamp = values.get('timestamp', 0)
    resistance_mohm = values.get('resistance_mohm')
    resistance_mohm = int(resistance_mohm)
  except (TypeError, ValueError):
    return False
  if not _valid_value(config, resistance_mohm):
    return False
  if not _recover_migrated_history(config.history_file_path, config):
    return False
  if not _migrate_legacy_history(config.history_file_path, config):
    return False
  row_values = [_timestamp_to_csv(timestamp), resistance_mohm]
  for name in (
      'before_voltage_x100', 'before_current_x100',
      'after_voltage_x100', 'after_current_x100',
      'delta_voltage_x100', 'delta_current_x100',
      'bms_temperature_c_x100', 'load_current_min_x100',
      'load_current_max_x100'):
    value = values.get(name)
    row_values.append(value if isinstance(value, int) else 'na')
  row = ','.join(str(value) for value in row_values) + '\n'
  path = config.history_file_path
  if _file_size(path) == 0 and _file_size(path + '.rotate.tmp') > 0:
    recovered_row = _recover_rotated_history(path, config)
    if recovered_row is None:
      return False
    if recovered_row == row:
      return True
  current_size = _file_size(path)
  if current_size is None:
    return False
  tail_is_complete = _history_tail_is_complete(path, current_size)
  tail_marker = '' if tail_is_complete else ',invalid\n'
  required_size = (
    len(row) +
    (len(_HISTORY_HEADER) if current_size == 0 else 0) +
    len(tail_marker)
  )
  if current_size and current_size + required_size > \
      config.history_file_max_bytes:
    temporary_path = path + '.rotate.tmp'
    try:
      with open(temporary_path, 'w') as history:
        history.write(_HISTORY_HEADER)
        history.write(row)
    except OSError:
      return False
    if not _remove_if_present(path):
      return False
    try:
      _fs.rename(temporary_path, path)
    except OSError:
      return False
    return True
  try:
    with open(path, 'a') as history:
      if current_size == 0:
        history.write(_HISTORY_HEADER)
      elif tail_marker:
        # Make a reset-truncated tail unambiguously invalid and terminate it,
        # so this boot's complete row cannot become attached to it.
        history.write(tail_marker)
      history.write(row)
  except OSError:
    return False
  return True


def _append_history(state, config):
  if state.battery_resistance_last_mohm is None:
    return True
  return _append_history_record((
    state.battery_resistance_last_timestamp,
    state.battery_resistance_last_mohm,
    getattr(state, 'battery_resistance_last_bms_temperature_c_x100', None),
  ), config)


def _summary_lines(state):
  return (
    _SUMMARY_HEADER + '\n',
    'last,{},{}\n'.format(
      state.battery_resistance_last_mohm,
      _timestamp_to_csv(state.battery_resistance_last_timestamp),
    ),
    'min,{},{}\n'.format(
      state.battery_resistance_min_mohm,
      _timestamp_to_csv(state.battery_resistance_min_timestamp),
    ),
    'max,{},{}\n'.format(
      state.battery_resistance_max_mohm,
      _timestamp_to_csv(state.battery_resistance_max_timestamp),
    ),
  )


def _save_summary_atomic(state, config):
  path = config.summary_file_path
  temporary_path = path + '.tmp'
  try:
    with open(temporary_path, 'w') as summary:
      for line in _summary_lines(state):
        summary.write(line)
  except OSError:
    # The primary has not been touched, so it remains the recovery generation.
    return False

  # The loader accepts a complete .tmp as the newest generation. Therefore
  # removing the old primary before rename no longer creates a no-data window.
  if not _remove_if_present(path):
    return False

  try:
    _fs.rename(temporary_path, path)
  except OSError:
    # Leave the validated temporary generation for next-boot recovery.
    return False
  return True


def save_battery_resistance_history(state, config):
  """Commit history first, then atomically publish its matching summary."""
  dirty = bool(state.battery_resistance_history_dirty)
  pending_records = getattr(
    state, 'battery_resistance_pending_records', None)
  if pending_records:
    dirty = True
  repair = bool(getattr(
    state, 'battery_resistance_summary_repair_pending', False))
  migration_repair = bool(getattr(
    state, 'battery_resistance_history_migration_repair_pending', False))
  if not dirty and not repair and not migration_repair:
    return True

  if migration_repair:
    if not _recover_migrated_history(config.history_file_path, config):
      return False
    state.battery_resistance_history_migration_repair_pending = False

  if pending_records is not None:
    # Each completed result gets its own committed row. Remove a record from
    # RAM only after its append succeeds. History is authoritative during
    # next-boot recovery if power disappears before the matching summary is
    # published.
    while pending_records:
      if not _append_history_record(pending_records[0], config):
        return False
      pending_records.pop(0)

    if not _save_summary_atomic(state, config):
      return False

    state.battery_resistance_history_dirty = False
    state.battery_resistance_history_row_saved = False
    state.battery_resistance_summary_repair_pending = False
    state.battery_resistance_history_migration_repair_pending = False
    return True

  row_saved = bool(getattr(
    state, 'battery_resistance_history_row_saved', False))
  if dirty and not row_saved:
    if not _append_history(state, config):
      return False
    state.battery_resistance_history_row_saved = True

  if not _save_summary_atomic(state, config):
    return False

  state.battery_resistance_history_dirty = False
  state.battery_resistance_history_row_saved = False
  state.battery_resistance_summary_repair_pending = False
  state.battery_resistance_history_migration_repair_pending = False
  return True
