# Firmware Issues Review

Review date: 2026-10-05.

Scope: maintained scooter firmware: Motor Board, Display, Lights Board, Power
Board, shared ESP-NOW helpers, and runtime configuration.
Legacy e-bike paths are excluded. The review covers the current `main` branch
after removal of the battery-resistance feature. Prior remediation of BMS-06,
BMS-08, DEP-01, and RTC-01 is recorded in
`firmware_fix_log_2026-09-21.md`; performance work is in `OPTIMIZATIONS.md`.

Open findings are listed below. Fixes from this review are recorded at the end.

## Open findings

| ID | Evidence | Severity | Finding |
| --- | --- | --- | --- |
| LT-01 | Receiver behavior | Medium | Lights ownership is selected from `mask`, not enforced by `src`. |
| SEC-01 | Protocol architecture | High | ESP-NOW command frames are unauthenticated and replayable. |
| SYS-01 | Critical tasks lack supervision | High | No supervisor or watchdog recovery. |
| PWR-01 | Protocol architecture | Medium | Relay/configuration delivery has no application acknowledgement. |
| PWR-04 | Power configuration | Medium | Runtime configuration is echoed as applied even if NVS persistence fails. |
| MOT-01 | Required CAN timing delay | Medium | CAN sends can still postpone the 20 ms motor cycle. |
| CHG-01 | BMS sampling | Medium | One BASIC current sample can satisfy the charging hold interval. |
| UI-01 | LCD flush error handling | Medium | Display transfer failures are silently discarded. |
| RTC-02 | UDP time response validation | Medium | An unrelated UDP reply can set the RTC and affect scheduled lights. |
| DEP-02 | Incremental updater | Medium | An unreadable or corrupt manifest can leave obsolete firmware files on the device. |

## Intentional design decisions

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

### PWR-04 — applied power settings may not survive a reboot

**Status:** Open. **Severity:** Medium.

On a configuration change, the Power Board updates its live values and
accelerometer, then ignores the return value from `save_power_settings_to_nvs()`
and queues a normal configuration echo. The Display can report the echoed
values as applied even when flash persistence failed; the next boot can load
the older settings.

**References:** `04_diy_automatic_power_control/main.py:398-424` and
`02_diy_display/escooter/main.py:1145-1160`.

**Recommended action:** distinguish volatile application from committed
settings in the echo, retry failed persistence, and alert when the saved
configuration differs from the live configuration.

### CHG-01 — charging hold is counted across repeated reads of one BMS frame

**Status:** Open. **Severity:** Medium.

The Display accepts a BASIC frame for up to three seconds, republishes its
current and timestamp every second, and checks that cached current in a 50 ms
task. The dual-motor profile uses a 1000 ms charging hold while BASIC and cell
queries alternate at roughly one-second intervals. One qualifying current
frame can therefore start and finish the hold before a second BASIC frame
arrives; one low-current frame can similarly end a charging session.

**References:** `02_diy_display/escooter/main.py:245-283`,
`02_diy_display/escooter/main.py:892-936`, and
`config_escooter_dual_motor_iscooter_i12.py:136-137`.

**Recommended action:** advance the hold only on distinct, post-stop BASIC
timestamps, or require a configured number of fresh frames. Replay a single
positive and single low-current frame through the charging flow.

### UI-01 — LCD transfer errors are hidden

**Status:** Open. **Severity:** Medium.

`ScreenManager.render()` catches every exception from `fb.show()` and silently
continues. A persistent SPI/LCD failure can leave the displayed speed or
warning stale while the UI task appears healthy; it also hides the cause from
diagnostics.

**References:** `02_diy_display/screen_manager.py:88-95` and
`02_diy_display/escooter/main.py:692-709`.

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

### DEP-02 — updater loses cleanup ownership when the manifest cannot be read

**Status:** Open. **Severity:** Medium.

The incremental updater treats any `mpremote fs cat` failure as an empty
previous manifest. It then uploads current files and publishes a new manifest,
but has no old paths to remove. A transient read failure or malformed manifest
can leave deleted modules on the device permanently, including modules
removed from the source tree; a missing first-install manifest is
indistinguishable from this case.

**References:** `scripts/update_firmware.sh:67-70`,
`scripts/update_firmware.sh:101-131`, and
`common/config_runtime.py:37-52`.

**Recommended action:** distinguish a first install from an unreadable or
invalid manifest. Abort on read/format failure or enumerate known managed
paths before replacing the manifest; test the interrupted-update case.

## Review and validation — 2026-10-05

- Reviewed active scooter code paths on all four boards, shared communications,
  BMS charging detection, configuration loading, and the incremental updater.
- The current host suite passed 37 tests; `bash -n scripts/update_firmware.sh`
  passed. These checks do not reproduce the newly documented failure cases.
- A focused host replay confirmed both UI-02 transitions, including motor
  enable after a single acknowledgement press; it did not exercise hardware.
- No target-hardware CAN/BLE/radio timing, relay-fault injection, flash-failure,
  or network spoofing test was performed. Severity reflects the code path and
  possible effect; hardware behavior still needs confirmation.

## Resolved in code — 2026-10-05

| ID | Change | Remaining hardware check |
| --- | --- | --- |
| UI-02 | Charging reconfirmation now waits until the failure screen has been shown, consumes only a subsequent long-press event, and returns before normal Ready input processing. | Confirm button timing on the Display. |
| PWR-03 | Relay outputs are deasserted if startup fails or the run loop exits, including on an exception. | Confirm physical relay polarity and fault behavior on the Power Board. |
| MOT-03 | Cruise clears its target when rear Status-1 telemetry becomes stale, and requires a fresh long-press edge after telemetry returns. | Confirm receive-only CAN loss and recovery on the Motor Board. |
