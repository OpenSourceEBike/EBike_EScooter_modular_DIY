# Firmware Issues Review

Review date: 2026-09-18.

Scope: maintained scooter firmware in this checkout: motor, Display, lights,
automatic power-control board, shared ESP-NOW helpers, runtime configuration,
and the battery-resistance feature. The legacy e-bike paths are excluded. This
revision includes a post-implementation review of the Display-local JBD BMS
battery-resistance path.

Only open findings are kept in this file. The two intentional design decisions
below are recorded solely to prevent them being reintroduced as issues.

## Open findings

| ID | Probability / evidence | Severity | Open finding |
| --- | --- | --- | --- |
| SEC-02 | Certain; unconditional prints in both Wi-Fi connection paths | Medium | Wi-Fi passwords are written verbatim to the serial log. |
| DEP-01 | Certain when changing the selected config through the updater | Medium | Incremental deployment leaves the previous root config behind, so the next boot aborts. |
| BMS-01 | Certain malformed-frame path; runtime frequency unknown | Low | A bad JBD frame terminator consumes one byte beyond that frame. |
| LT-01 | Known receiver behavior; sender contract normally prevents it | Medium | Lights ownership is selected from `mask`, not enforced from `src`. |
| SEC-01 | Certain architectural exposure; incident likelihood not measured | High | ESP-NOW command frames are unauthenticated and replayable. |
| SYS-01 | Certain architectural gap | High | Critical tasks have no supervisor or watchdog recovery. |
| PWR-01 | Certain protocol gap | Medium | Relay and power configuration are not application-acknowledged. |
| MOT-01 | Required CAN delay; target timing not measured | Medium | Synchronous post-send delays can still postpone the nominal 20 ms motor cycle. |
| RTC-01 | Certain blocking call; duration requires target-network measurement | Medium | Asynchronous NTP synchronization still invokes a synchronous operation. |

## Intentional design decisions (not issues)

### BMS-02 — MOSFET state is intentionally ignored

The JBD client does not expose and the BMS resistance estimator does not read
or use charge/discharge MOSFET state. A disabled, enabled, or unavailable
MOSFET state neither blocks nor resets a measurement. This is an intentional
design decision, not an issue.

### PWR-02 — relay is asserted before peripheral initialization

The Power Board intentionally asserts the relay at the first possible point,
before radio, I2C, and ADXL345 initialization, so the Display is powered during
Power Board startup. A startup exception after that assertion is accepted
behavior for this design and is not an issue.

## Lights and communications

### LT-01 — lights ownership is selected from mask

**Status:** Open; established behavior restored. **Severity:** Medium.

The lights receiver accepts Display and motor sources but selects the
brake/display state path from `mask`, not from `src`. Source enforcement was
reverted to restore the existing receiver behavior.

**References:**

- `03_diy_lights_board/main.py:92-98`
- `03_diy_lights_board/main.py:167-184`
- `common/lights_bits.py:1-21`

**Impact:** a malformed or forged Display frame containing the brake bit can
refresh the motor-owned state; a motor frame without it can reach the
Display-owned path. Current encoders are expected to preserve ownership.

**Recommended action:** keep the restored behavior unless a future hardware
integration test explicitly validates a source-enforced replacement.

### SEC-01 — ESP-NOW commands are unauthenticated

**Status:** Open. **Severity:** High.

Frames are plain ASCII with numeric source/destination IDs. Receivers validate
the payload IDs but do not bind them to the received peer MAC, authenticate the
payload, or reject replayed commands.

**References:**

- `common/espnow_protocol.py:18-34`
- `01_diy_main_board/escooter/main.py:399-430`
- `03_diy_lights_board/main.py:91-97`
- `04_diy_automatic_power_control/main.py:186-196`

**Impact:** a radio sender able to forge a valid frame can request motor state,
lights, relay shutdown, or power configuration changes.

**Recommended action:** validate peer MAC ownership, configure encrypted peers,
and add a replay-resistant counter/nonce if supported by the deployed
MicroPython ESP-NOW stack.

### SEC-02 — Wi-Fi password is printed verbatim

**Status:** Open. **Severity:** Medium.

Both synchronous and asynchronous Wi-Fi connection attempts print
`repr(password)` unconditionally. The production charging-time NTP path uses
the asynchronous function, so every attempted sync writes the configured Wi-Fi
password to the Display serial output.

**References:**

- `02_diy_display/wifi_time_sync.py:194-203`
- `02_diy_display/wifi_time_sync.py:223-234`
- `02_diy_display/escooter/main.py:790-876`

**Impact:** anyone with access to captured serial logs or a connected console
can recover the network credential. Debug flags do not suppress the output.

**Recommended action:** remove both password prints. If connection diagnostics
are needed, log only whether a non-empty credential was supplied.

## Deployment integrity

### DEP-01 — selecting a different config leaves two root configs

**Status:** Open. **Severity:** Medium.

The updater copies the selected `config_*.py` and publishes a manifest containing
only the new selection, but it removes only board-specific entries from the
hard-coded `OBSOLETE_FILES` list. A previously deployed config with another
filename remains at the device root. The runtime loader deliberately aborts
when more than one root config exists.

**References:**

- `scripts/update_firmware.sh:16-21`
- `scripts/update_firmware.sh:58-102`
- `common/config_runtime.py:27-53`

**Impact:** switching, for example, from dual-motor to single-motor config with
the normal update script produces a board that fails at the next boot.

**Recommended action:** before publishing the new manifest, remove every old
manifest entry matching `/config_*.py` except the selected destination. Treat a
failed config removal as a deployment failure and do not reset the board.

## BMS stream recovery

### BMS-01 — malformed terminator skips the next byte

**Status:** Open; malformed-input edge. **Severity:** Low.

`_pop_frame()` advances `_head` by the full declared frame length before
checking the `0x77` terminator. If the terminator is wrong, it advances `_head`
once more. When the next byte is the `0xDD` start of a valid following frame,
that start byte is discarded too.

**References:**

- `02_diy_display/bms_jbd.py:396-430`

**Impact:** one malformed notification can also discard the immediately
following valid JBD frame, extending BMS-current staleness and delaying charging
recognition or post-NTP charging re-confirmation.

**Recommended action:** after consuming the malformed declared frame, resume at
the current `_head`; do not increment again. Add a parser test containing a bad
frame immediately followed by a valid BASIC frame.

## Runtime supervision and timing

### SYS-01 — no supervisor or watchdog recovery

**Status:** Open. **Severity:** High.

The motor and Display run critical coroutines under `asyncio.gather()` without a
supervisor. There is no active hardware watchdog. The power board also relies
on its main loop continuing in order to reach normal timeout shutdown.

**References:**

- `01_diy_main_board/escooter/main.py:805-821`
- `02_diy_display/escooter/main.py:1306-1319`
- `04_diy_automatic_power_control/main.py:354-476`

**Impact:** an uncaught task exception or peripheral lock-up can leave a board
degraded or keep the power path asserted until external intervention.

**Recommended action:** supervise critical tasks, apply a software-safe state
on failure, and reset promptly. Feed any reintroduced hardware watchdog only
after a complete critical cycle; validate relay state after watchdog reset on
target hardware.

### MOT-01 — required CAN delays can postpone the 20 ms cycle

**Status:** Open; requires hardware measurement. **Severity:** Medium.

Each successful CAN transmission retains the required 3 ms ESP32 delay. The
normal 20 ms loop now sends only one actuation command per configured VESC, but
the separate 100 ms task sends the two persistent limit commands per VESC.
CAN receive no longer waits on an empty queue and is bounded to 32 queued
frames per refresh.

**References:**

- `01_diy_main_board/escooter/main.py:494-656`
- `01_diy_main_board/escooter/main.py:658-725`
- `01_diy_main_board/motor.py:68-97`
- `01_diy_main_board/motor.py:123-194`

**Impact:** in dual-motor operation, cooperative scheduling can still delay an
actuation cycle when it coincides with the limit-refresh task.

**Recommended action:** measure worst-case loop latency on the ESP32-S3 with
dual VESC traffic while retaining the proven 3 ms post-send delay.

### RTC-01 — synchronous NTP call inside asynchronous flow

**Status:** Open; requires target-network measurement. **Severity:** Medium.

`sync_rtc_time_from_wifi_ntp_async()` ultimately calls synchronous
`ntptime.settime()`. During that call the Display event loop cannot schedule UI
or recovery work, while ESP-NOW and BLE are deliberately paused.

**References:**

- `02_diy_display/wifi_time_sync.py:334-387`
- `02_diy_display/escooter/main.py:790-876`

**Impact:** slow DNS/NTP behavior can freeze the Display longer than expected
and delay radio recovery.

**Recommended action:** measure worst-case duration on the deployed network.
If unacceptable, use a bounded NTP implementation or isolate the blocking
operation from the normal UI/communication scheduler.

## Power-control acknowledgement

### PWR-01 — relay/config delivery is not application-acknowledged

**Status:** Open. **Severity:** Medium.

The Display treats a successful ESP-NOW send as power-board health. The power
board echoes configuration only after an accepted value changes and does not
report actual relay state or acknowledge each `turn_off` request. The Display
also marks configuration as sent after MAC-level success rather than after a
matching echo.

**References:**

- `02_diy_display/escooter/main.py:181-235`
- `02_diy_display/escooter/main.py:346-367`
- `02_diy_display/escooter/main.py:1142-1250`
- `04_diy_automatic_power_control/main.py:186-263`
- `04_diy_automatic_power_control/main.py:357-423`

**Impact:** the Display cannot distinguish applied, rejected, already-present,
or merely transmitted state, and cannot confirm that the relay physically
followed the request.

**Recommended action:** add status containing relay state, applied
configuration, last command identifier, and power-off reason. Echo valid
configuration commands even when values do not change, and base Display state
on a fresh matching acknowledgement.

## Validation performed

- Syntax compilation succeeded for all 91 Python files in the checkout.
- Twenty-one host tests passed: BMS resistance configuration and state-machine
  behavior, operational CAN telemetry decode, Motor Board timing, telemetry
  helpers, and battery-resistance screen navigation.
- Targeted BMS tests cover a known 35 mOhm step, duplicate BASIC timestamp
  rejection, regeneration not starting a discharge event, active-protection
  rejection, power-window/load-threshold behavior, variable sustained load,
  and load-event expiry.
- Motor CAN tests cover standard VESC Status 1/4/5 and rear SOC command `99`;
  a former private precision command is ignored. Telemetry tests cover the
  unavailable-temperature sentinel after Status-4 expiry.
- `git diff --check` passed.
- No live JBD BLE/BASIC cadence, ESP32-S3 UI timing/heap, CAN, radio,
  filesystem power-loss, or target-network timing test was performed.
