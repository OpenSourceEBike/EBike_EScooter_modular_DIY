# Firmware Issues Review

Review date: 2026-09-23.

Scope: maintained scooter firmware: Motor Board, Display, Lights Board, Power
Board, shared ESP-NOW helpers, runtime configuration, and battery resistance.
Legacy e-bike paths are excluded. Remediation of BMS-06, BMS-07, BMS-08,
DEP-01, and RTC-01 is recorded in `firmware_fix_log_2026-09-21.md`; the
ESP32-S3 runtime allocation/redraw work is recorded in `OPTIMIZATIONS.md`.

Only open findings are kept in this file.

## Open findings

| ID | Evidence | Severity | Finding |
| --- | --- | --- | --- |
| BMS-05 | NTC order has no configuration | Low | Logged BMS temperature is always unnamed JBD NTC 1. |
| LT-01 | Receiver behavior | Medium | Lights ownership is selected from `mask`, not enforced by `src`. |
| SEC-01 | Protocol architecture | High | ESP-NOW command frames are unauthenticated and replayable. |
| SYS-01 | Critical tasks lack supervision | High | No supervisor or watchdog recovery. |
| PWR-01 | Protocol architecture | Medium | Relay/configuration delivery has no application acknowledgement. |
| MOT-01 | Required CAN timing delay | Medium | CAN sends can still postpone the 20 ms motor cycle. |
| UI-01 | LCD flush error handling | Medium | Display transfer failures are silently discarded. |
| RTC-02 | UDP time response validation | Medium | An unrelated UDP reply can set the RTC and affect scheduled lights. |

## Intentional design decisions

### BMS-02 — MOSFET state is intentionally ignored

The JBD client and resistance estimator do not use charge/discharge MOSFET
state. A disabled, enabled, or unavailable MOSFET state neither blocks nor
resets a measurement.

### PWR-02 — relay is asserted before peripheral initialization

The Power Board asserts the relay as early as possible, before radio, I2C, and
ADXL345 initialization, so the Display has power during startup.

### SEC-02 — Wi-Fi password in serial diagnostics

The synchronous and asynchronous Wi-Fi connection paths print the password on
the serial console. This behavior is explicitly retained for diagnostics and
is not scheduled for correction. Access to serial output must therefore be
treated as access to the Wi-Fi credential.

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

### UI-01 — LCD transfer errors are hidden

**Status:** Open. **Severity:** Medium.

`ScreenManager.render()` catches every exception from `fb.show()` and silently
continues. A persistent SPI/LCD failure can leave the displayed speed or
warning stale while the UI task appears healthy; it also hides the cause from
diagnostics.

**References:** `02_diy_display/screen_manager.py:104-109` and
`02_diy_display/escooter/main.py:851-868`.

**Recommended action:** record a bounded error count and last error, expose
display health, and define a safe response to repeated failures. Avoid
unbounded logging in the 100 ms UI task.

### RTC-02 — Wi-Fi time response is not tied to its request

**Status:** Open. **Severity:** Medium.

The asynchronous UDP helper returns the first nonempty datagram without
checking its source. The NTP request has no unique transmit timestamp, and
the response is accepted using only length, mode, and stratum before the RTC
is set. A stray or forged UDP reply during synchronization can therefore
change the clock and the automatic-light schedule. DNS replies likewise
check the transaction ID but not the requested name.

**References:** `02_diy_display/wifi_time_sync.py:53-96`,
`02_diy_display/wifi_time_sync.py:111-194`, and
`02_diy_display/escooter/main.py:669-697`.

**Recommended action:** check UDP source IP/port, match the NTP originate
timestamp to a per-request transmit timestamp, validate the DNS question and
answer name, and reject implausible time jumps. Test with wrong-source and
wrong-request packets.

## Validation performed

- 59 host tests passed, covering BMS state/persistence/recovery, ESP-NOW,
  CAN decoding/timing, telemetry, screen navigation, display rendering,
  throttle refresh, and asynchronous Wi-Fi/NTP helpers. The new telemetry
  tests cover MOT-02 recovery at identical ERPM and unchanged-ERPM caching.
- `git diff --check` passed.
- No live ESP32-S3 heap/jitter, CAN/radio, BLE, power-loss, updater, or
  target-network timing validation was performed.
- New findings above are based on code-path review; no physical fault
  injection or LCD/RTC hardware test was performed. MOT-02 is resolved in the
  current source but still needs a live CAN-loss/recovery check.
