# Firmware Issues Review

Review date: 2026-07-26.

Scope: active MicroPython firmware in this checkout, with focus on the maintained escooter display, motor, lights, automatic power control board, shared ESP-NOW helpers, and config runtime. The e-bike path is documented as legacy/not maintained and is not part of the active maintained firmware scope.

Validation done:

- CPython syntax-only `py_compile` passed for the active entry points and
  critical shared modules.
- `pyflakes` and `ruff` are not installed in this environment, so no external static linter pass was run.
- `mpy-cross` is not installed in this environment, so no MicroPython parser/compiler pass was run.
- No hardware test was done in this review.

This file tracks currently open findings. Older findings already marked implemented are intentionally removed from the active list.

Resolved since the previous review: the power-board production logging default is
disabled (`debug_enable = False`), forced GC calls were removed from the
high-frequency motor, lights, and power-control loops, lights retries now use a
bounded backoff, charging reconfirmation failures are shown as an explicit
unknown state, and button timing/event delivery was hardened.

## Recently resolved findings

### Lights retry traffic was unbounded during an outage

**Status:** Resolved.

Display and motor-board lights transmissions now retry with an exponential
interval starting at 50 ms and capped at 1000 ms. Jitter remains applied to
avoid synchronized retries, and a successful send resets the interval.

### Charging reconfirmation timeout silently reported non-charging

**Status:** Resolved.

After the 10-second evidence window, the display enters an explicit
`charging unknown` state instead of silently presenting non-charging. The
charging screen remains protected until the rider acknowledges it with a power
long press or fresh BMS evidence resolves the state.

### Manual lights and automatic schedule policy was implicit

**Status:** Resolved.

The maintained switch remains a manual ON override by default. Deployments that
require the schedule to be authoritative can set
`auto_lights_schedule_authoritative = True` in the selected configuration.

### Button timing used an incompatible tick source and UI events could be lost

**Status:** Resolved.

`thisButton` now uses `ticks_us()` with `ticks_diff()`/`ticks_add()`. Short clicks
are accepted from 100 ms, long presses from 1000 ms, and power-button events are
latched until the UI task consumes them. The display also suppresses the
transient re-arm warning after leaving the charging screen while preserving the
motor-board safety latch.

## Review Summary

| Severity | Open findings |
| --- | --- |
| High | ESP-NOW command frames are not authenticated; active critical tasks have no supervisor. |
| Medium | Relay state has no application acknowledgement; motor-cycle timing is unmeasured; NTP remains blocking. |

## Findings

### High - ESP-NOW command frames are not authenticated

**Status:** Open.

The shared protocol is plain ASCII and carries only numeric source/destination
board IDs. The active receivers validate those fields but do not validate the
received peer MAC address or authenticate the payload.

**References:**

- `common/espnow_protocol.py:14-30`
- `01_diy_main_board/escooter/main.py:298-309`
- `03_diy_lights_board/main.py:166-180`
- `04_diy_automatic_power_control/main.py:186-195`

**Impact:** a radio sender able to forge a valid frame can request motor state,
lights, relay shutdown, or power configuration changes.

**Recommended action:** validate the peer MAC against the expected board for
each link, configure encrypted ESP-NOW peers, and add a replay-resistant
counter/nonce if the platform supports it.

### High - active critical tasks have no supervisor or watchdog recovery

**Status:** Open.

The active scooter firmware no longer creates or feeds a hardware watchdog.
The power board asserts relay outputs at startup and its normal timeout-based
power-off logic only runs while the main loop continues executing. The motor
and display applications also have no task supervisor to recover an
unexpectedly terminated critical task.

**References:**

- `01_diy_main_board/escooter/main.py:708-724`
- `02_diy_display/escooter/main.py:921-928`
- `04_diy_automatic_power_control/main.py:354-465`

**Impact:** a firmware or peripheral lock-up can leave the power path asserted
until an external reset or power intervention. An uncaught exception can also
stop motor or display tasks while the remaining firmware continues running.

**Recommended action:** add an explicit supervisor that places actuators in a
safe state and restarts promptly after a critical task failure. If a hardware
watchdog is reintroduced, feed it only after the complete critical cycle and
test the relay state after watchdog reset on target hardware.

### Medium - relay command delivery is not application-acknowledged

**Status:** Open.

The Display treats a successful ESP-NOW send as power-board communication
health. The power board emits configuration echoes, but does not send its
actual relay state or an acknowledgement tied to each `turn_off` command.

**References:**

- `02_diy_display/escooter/main.py:804-829`
- `04_diy_automatic_power_control/main.py:364-367`

**Impact:** the Display can report communication as healthy even if the relay
command was received but could not be applied by the power board.

**Recommended action:** add a power-board status frame containing relay state,
last command identifier, and power-off reason; make Display health depend on a
fresh matching acknowledgement.

### Medium - motor control timing has blocking work in the 20 ms loop

**Status:** Open; requires hardware measurement.

The motor-control coroutine targets 20 ms but can make multiple CAN sends per
iteration. Each successful send calls `time.sleep_ms(3)`. CAN telemetry drain
also reserves up to 10 ms in a separate cooperative task.

**References:**

- `01_diy_main_board/escooter/main.py:375-526`
- `01_diy_main_board/motor.py:75-77`
- `01_diy_main_board/motor.py:111-116`

**Impact:** with two motors, real control and ESP-NOW latency can exceed the
nominal cadence, particularly under CAN traffic.

**Recommended action:** instrument worst-case task duration on the board,
review the 3 ms post-send delay, and bound the CAN work performed per cycle.

### Medium - task exceptions are not recovered explicitly

**Status:** Open.

Both active asynchronous applications use `asyncio.gather()` without a task
supervisor. An uncaught exception terminates the affected task and there is no
active hardware watchdog to provide recovery.

**References:**

- `01_diy_main_board/escooter/main.py:708-724`
- `02_diy_display/escooter/main.py:921-928`

**Impact:** a software fault can leave the firmware degraded indefinitely. The
safe behaviour of attached motor controllers during that interval is not
guaranteed by this firmware.

**Recommended action:** add a top-level supervisor that logs the failing task,
applies a software-safe state when possible, and resets promptly; validate with
fault injection on hardware.

### Medium - asynchronous NTP sync still contains a blocking operation

**Status:** Open; requires target-network measurement.

`sync_rtc_time_from_wifi_ntp_async()` calls the synchronous
`ntptime.settime()`. During this period the Display pauses ESP-NOW, and the
event loop cannot schedule normal UI and communication work.

**References:**

- `02_diy_display/wifi_time_sync.py:303-351`
- `02_diy_display/escooter/main.py:613-641`

**Impact:** slow DNS/NTP behaviour can freeze the Display longer than expected
and delay recovery of normal communication.

**Recommended action:** measure the worst case with the deployed network. If
it is unacceptable, use a bounded NTP implementation or isolate the operation
so normal UI and communication tasks remain responsive.
