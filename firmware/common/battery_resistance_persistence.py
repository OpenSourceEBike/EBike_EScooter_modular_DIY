import time

try:
  import uos as _fs
except ImportError:
  import os as _fs


_SUMMARY_HEADER = 'kind,resistance_mohm,timestamp'
_HISTORY_HEADER = 'timestamp,resistance_mohm\n'


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
      if history.readline() != _HISTORY_HEADER:
        return None
      for line in history:
        # A reset during append may leave a syntactically plausible prefix
        # (for example "...,8" instead of "...,83"). Only newline-terminated
        # records are committed records.
        if not line.endswith('\n'):
          continue
        parts = line.strip().split(',')
        if len(parts) != 2:
          continue
        timestamp, value = parts
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
  state.battery_resistance_min_mohm = summary['min'][0]
  state.battery_resistance_min_timestamp = summary['min'][1]
  state.battery_resistance_max_mohm = summary['max'][0]
  state.battery_resistance_max_timestamp = summary['max'][1]


def load_battery_resistance_history(state, config):
  """Load and reconcile recoverable summary generations with history."""
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

  history = _read_history(config.history_file_path, config)
  merged = _merge_summary_and_history(summary, history)
  if merged is None:
    return False

  _apply_summary(state, merged)
  state.battery_resistance_summary_repair_pending = (
    summary_path != path or merged != summary
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


def _append_history(state, config):
  if state.battery_resistance_last_mohm is None:
    return True
  row = '{},{}\n'.format(
    _timestamp_to_csv(state.battery_resistance_last_timestamp),
    state.battery_resistance_last_mohm,
  )
  path = config.history_file_path
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
    if not _remove_if_present(path):
      return False
    current_size = 0
    tail_marker = ''
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
  repair = bool(getattr(
    state, 'battery_resistance_summary_repair_pending', False))
  if not dirty and not repair:
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
  return True
