# Firmware Issues Review

Review date: 2026-07-09.

Scope: active MicroPython firmware in this checkout, with focus on the maintained escooter display, motor, lights, automatic power control board, shared ESP-NOW helpers, and config runtime. The e-bike path is documented as legacy/not maintained and is not part of the active maintained firmware scope.

Validation done:

- CPython syntax-only `compile()` passed on 79 Python files.
- `pyflakes` and `ruff` are not installed in this environment, so no external static linter pass was run.
- `mpy-cross` is not installed in this environment, so no MicroPython parser/compiler pass was run.
- No hardware test was done in this review.

This file tracks currently open findings. Older findings already marked implemented were intentionally removed from the active list. There is currently one open finding.
Resolved since the last pass: the root config deployment convention is documented, the legacy minutes compatibility path was removed, the charging hold sentinel was fixed, the ADXL345 INT1 routing is explicit, the ADXL345 setup now enables only the activity interrupt, the ESP-NOW protocol docs now match the no-sequence frame shapes, the display now throttles power-config retries instead of sending them every comm loop, the Boot click now evaluates the stopped/brakes-on Charging transition before the Boot-to-Main transition, `cfg` object fields are merged before optional defaults in the config loader, power config `ac_mode` validation is strict, the lights board inline ESP-NOW message comment now matches the current frame shape, the power-board relay pin map was moved off the ADXL345 I2C pins, the power board clears stale ADXL345 motion interrupts before arming deep-sleep wake, the active display button timing now uses config values, BMS debug logging is now config-driven and disabled by default, BMS comments now correctly state that only BLE scanning is deferred, and the e-bike path was marked legacy/not maintained.

## Review Summary

- Low: power board debug logging is enabled by default.

## Findings

### Low - power board debug logging is enabled by default

`debug_enable` is currently `True` on the automatic power control board.

Reference:

- `04_diy_automatic_power_control/main.py:23`

Impact: the board prints startup, timeout, motion, and sleep messages in normal operation. This is useful during tuning, but noisy for production and can slow the loop slightly.

Suggested fix: set `debug_enable = False` for the normal firmware image, or move it into config.
