# Firmware Issues Review

Review date: 2026-09-21.

Scope: maintained scooter firmware: Motor Board, Display, Lights Board, Power
Board, shared ESP-NOW helpers, runtime configuration, and battery resistance.
Legacy e-bike paths are excluded. Remediation of BMS-06, BMS-07, BMS-08,
DEP-01, and RTC-01 is recorded in `firmware_fix_log_2026-09-21.md`; the
ESP32-S3 runtime allocation/redraw work is recorded in `OPTIMIZATIONS.md`.

Only open findings are kept in this file.

## Open findings

| ID | Evidence | Severity | Finding |
| --- | --- | --- | --- |
| SEC-02 | Password is printed in both Wi-Fi paths | Medium | Wi-Fi credentials are exposed on serial output. |
| BMS-05 | NTC order has no configuration | Low | Logged BMS temperature is always unnamed JBD NTC 1. |
| LT-01 | Receiver behavior | Medium | Lights ownership is selected from `mask`, not enforced by `src`. |
| SEC-01 | Protocol architecture | High | ESP-NOW command frames are unauthenticated and replayable. |
| SYS-01 | Critical tasks lack supervision | High | No supervisor or watchdog recovery. |
| PWR-01 | Protocol architecture | Medium | Relay/configuration delivery has no application acknowledgement. |
| MOT-01 | Required CAN timing delay | Medium | CAN sends can still postpone the 20 ms motor cycle. |

## Intentional design decisions

### BMS-02 — MOSFET state is intentionally ignored

The JBD client and resistance estimator do not use charge/discharge MOSFET
state. A disabled, enabled, or unavailable MOSFET state neither blocks nor
resets a measurement.

### PWR-02 — relay is asserted before peripheral initialization

The Power Board asserts the relay as early as possible, before radio, I2C, and
ADXL345 initialization, so the Display has power during startup.

## Findings

### SEC-01 — ESP-NOW commands are unauthenticated

**Status:** Open. **Severity:** High.

Frames are plain ASCII source/destination IDs. Receivers do not bind a payload
to the received peer MAC, authenticate it, or reject replayed commands.

**References:** `common/espnow_protocol.py`,
`01_diy_main_board/escooter/main.py`, `03_diy_lights_board/main.py`, and
`04_diy_automatic_power_control/main.py`.

**Recommended action:** validate MAC ownership, configure encrypted peers, and
add a replay-resistant counter or nonce if the deployed MicroPython ESP-NOW
stack supports it.

### SYS-01 — no supervisor or watchdog recovery

**Status:** Open. **Severity:** High.

Motor and Display critical coroutines run under `asyncio.gather()` without a
supervisor or active hardware watchdog. The Power Board likewise requires its
main loop to reach normal timeout shutdown.

**References:** `01_diy_main_board/escooter/main.py`,
`02_diy_display/escooter/main.py`, and
`04_diy_automatic_power_control/main.py`.

**Recommended action:** supervise critical tasks, transition to a safe state
on failure, and reset promptly. Feed a watchdog only after a complete critical
cycle and verify relay state on target hardware.

### SEC-02 — Wi-Fi password is printed verbatim

**Status:** Open. **Severity:** Medium.

Both synchronous and asynchronous Wi-Fi attempts print `repr(password)`.

**References:** `02_diy_display/wifi_time_sync.py` and
`02_diy_display/escooter/main.py`.

**Recommended action:** remove password output; diagnostics may state only
whether a non-empty credential was supplied.

### LT-01 — lights ownership is selected from mask

**Status:** Open; established behavior restored. **Severity:** Medium.

The receiver accepts Display and Motor sources but chooses the brake/display
path from `mask`, not `src`. Current encoders are expected to preserve
ownership.

**References:** `03_diy_lights_board/main.py` and `common/lights_bits.py`.

**Recommended action:** retain this behavior unless hardware integration tests
validate a source-enforced replacement.

### BMS-05 — logged BMS temperature has no selected-sensor contract

**Status:** Open. **Severity:** Low.

The parser exposes ordered unnamed NTC readings, but persistence stores index
zero as `bms_temperature_c_x100`.

**References:** `02_diy_display/bms_jbd.py`,
`02_diy_display/escooter/main.py`, and
`common/battery_resistance_persistence.py`.

**Recommended action:** add a validated `bms_temperature_sensor_index` and
document the physical probe for each BMS; store `na` when unavailable.

### MOT-01 — required CAN delays can postpone the 20 ms cycle

**Status:** Open; requires hardware measurement. **Severity:** Medium.

Each successful CAN transmission retains the required 3 ms ESP32 delay. In
dual-motor operation cooperative scheduling can still delay actuation when it
coincides with the 100 ms limit-refresh task.

**References:** `01_diy_main_board/escooter/main.py` and
`01_diy_main_board/motor.py`.

**Recommended action:** measure worst-case loop latency on target hardware
with dual VESC traffic while retaining the proven delay.

### PWR-01 — relay/config delivery is not application-acknowledged

**Status:** Open. **Severity:** Medium.

Display currently treats a successful ESP-NOW send as Power Board health. The
Power Board does not report actual relay state or acknowledge every request.

**References:** `02_diy_display/escooter/main.py` and
`04_diy_automatic_power_control/main.py`.

**Recommended action:** report relay state, applied configuration, command ID,
and power-off reason; base Display status on a fresh matching acknowledgement.

## Validation performed

- 53 host tests passed, covering BMS state/persistence/recovery, ESP-NOW,
  CAN decoding/timing, telemetry, screen navigation, display rendering,
  throttle refresh, and asynchronous Wi-Fi/NTP helpers.
- `git diff --check` passed.
- No live ESP32-S3 heap/jitter, CAN/radio, BLE, power-loss, updater, or
  target-network timing validation was performed.
