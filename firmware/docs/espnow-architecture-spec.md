# ESPNOW Architecture Spec

> Wiki entry point: [Firmware Wiki](../README.md)

## Purpose

This document describes the ESPNOW communication architecture implemented by the firmware.

The goal is to make board-to-board communication easier to reason about, easier to monitor, and able to report failures back to the display UI.

## Current Topology

Today the system has several ESPNOW participants:

- Display board
- Motor board
- Lights board
- Power-switch board, implemented in `04_diy_automatic_power_control/`

In the current codebase, the display can talk directly to the motor board, lights board, and power-switch board.
The motor board also talks directly to the lights board in the scooter firmware.

This creates overlapping ownership for some remote states, especially lights and power control.

## Active Topology

The scooter firmware currently uses direct links:

- Display board is the UI and user input source.
- Display sends motor commands to the motor board, rider-light commands to the
  lights board, and relay/config commands to the power-switch board.
- Motor board sends its brake-light bit to the lights board and status to the
  display.

Active communication rules:

- Display talks directly to the motor, lights, and power-switch boards.
- Motor board sends only `REAR_BRAKE_BIT` to the lights board.
- Display owns the rider-light bits; the lights board combines those with the
  motor-owned brake bit.

## Board Responsibilities

### Display board

- Collects user input.
- Renders status and errors.
- Sends user intent to the motor board.
- Receives board health and system state from the motor board.

### Motor board

- Controls the motors and receives the display enable/throttle intent.
- Sends only the motor-owned brake-light bit to the lights board.
- Tracks send results, received status frames, and timeouts.
- Maintains last known communication state for each remote board.
- Reports a compact system health summary back to the display.

### Lights board

- Applies light state requests.
- Uses safe defaults if comms stop arriving.

### Power-switch board

- Applies power relay / power-off control requests.
- Keeps the power path in a safe state if comms stop arriving.

## Message Contract

Current ESPNOW messages carry enough information to support:

- Request type
- Source board
- Target board
- Payload fields needed for the specific board action

Current common frame prefixes:

- Command: `MSG_COMMAND, src, dst, ...payload`
- Status: `MSG_STATUS, src, dst, health, ...payload`

Frames are ASCII numbers separated by spaces. They do not include a sequence field.

Current power-switch command IDs:

- `POWER_SWITCH_CMD = 1`
- `POWER_CONFIG_CMD = 2`

## Decisions

These implementation choices are currently settled:

- The payload remains ASCII.
- The motor board keeps a per-board health bitmap.
- The display shows one error per remote board.
- Command frames use `MSG_COMMAND, src, dst, ...payload`.
- Status frames use `MSG_STATUS, src, dst, health, ...payload`.
- There is no generic acknowledgement frame.
- Failed lights transmissions use a bounded exponential retry interval.

## Current Frame Shapes

Display to motor command:

```text
MSG_COMMAND src=BOARD_DISPLAY dst=BOARD_MOTOR motor_enable buttons lights turn_off
```

Display or motor to lights command:

```text
MSG_COMMAND src dst=BOARD_LIGHTS mask state
```

The display owns the rider-light bits and the motor board sends only
`REAR_BRAKE_BIT`. During Wi-Fi time sync, the display light state is outside
the sync/recovery contract.

The current senders follow this ownership, but the lights receiver selects the
brake/display path from `mask` rather than enforcing it from `src`. This keeps
the established receiver behavior without changing the frame.

Display or motor to power-switch relay command:

```text
MSG_COMMAND src dst=BOARD_POWER_SWITCH POWER_SWITCH_CMD turn_off
```

Display or motor to power-switch config command:

```text
MSG_COMMAND src dst=BOARD_POWER_SWITCH POWER_CONFIG_CMD motion_threshold motion_rate_hz motion_ac_mode timeout_seconds wait_seconds
```

Motor to display status:

```text
MSG_STATUS src=BOARD_MOTOR dst=BOARD_DISPLAY health battery_voltage_x10 battery_current_x10 battery_soc_x1000 motor_current_x10 wheel_speed_x10 flags rear_vesc_temp_x10 front_vesc_temp_x10 rear_motor_temp_x10 front_motor_temp_x10 battery_resistance_mohm resistance_phase resistance_boot_seconds resistance_retries resistance_load_samples resistance_reference_samples resistance_phase_seconds motion_can_losses thermal_can_losses
```

Status `flags` bit 2 carries `throttle_rearm_required`.
`battery_is_charging` is display-local state derived from the optional BLE BMS
and is not transported in motor status.

Motor-status health bits also report whether rear speed is fresh. VESC status
families have independent timestamps; receiving one family does not refresh the
others.

The battery-resistance estimator runs on the motor board. Existing field
meanings and order remain unchanged; the terminal
`battery_resistance_mohm` field is `-1` while no result is available and then
repeats the one `1..2500` mOhm result for the rest of the boot. It carries no
measurement timestamp, age, or sequence number.

Newer motor boards append six resistance diagnostic values followed by the
cumulative `102` motion and `103` thermal CAN sequence-gap counters. Older
Displays safely ignore these trailing values.

The Display latches that repeated result once per Display boot. Repeated frames
within the same boot do not duplicate history or alerts. If only the Display
restarts while the motor remains powered, the new local session accepts the
result once and shows one new alert.

Power-switch to sender config echo/status:

```text
MSG_STATUS src=BOARD_POWER_SWITCH dst health=0 motion_threshold motion_rate_hz motion_ac_mode timeout_seconds wait_seconds
```

## Status And Health Rules

- Motor status frames carry motor-to-lights TX health in `HEALTH_MOTOR_LIGHTS_TX_OK`.
- Power-switch config changes are echoed back as status frames with the validated values accepted by the board.
- Periodic switch commands can be sent for continuity.
- Power config commands should be sent only when config values change.
- Timeout detection is based on missing send success or missing received status, depending on the link.
- Receive loops drain all packets currently queued and retain only the most
  recent valid packet for each relevant source. Older queued packets are
  discarded instead of being processed sequentially.

ESP-NOW diagnostic logging is disabled by default through `espnow_debug = False`.
It should only be enabled temporarily for board-local troubleshooting.

## Display Error Policy

The display should show a clear error when a board-specific send/status timeout expires.

Examples:

- `lights comm error`
- `power board timeout`
- `motor board no reply`

The error should be raised when a board-specific send/status timeout expires.

The display should keep showing the last known good state alongside the error whenever possible.

## State Ownership

Each remote state should have exactly one owner.

Expected ownership:

- Rider/automatic light request: display owns the request and sends its bits
  directly; lights board owns the output pins.
- Brake light: motor board owns `REAR_BRAKE_BIT`; lights board owns the output.
- Power-off state: display owns the request flow; power-switch board owns the
  relay state.
- Motor/display link: motor board owns motor safety and reports status to the
  display.

## Charging Wi-Fi time sync

When enabled, the display schedules one NTP sync on the first transition into
`CHARGING` after boot. The delay is 2000 ms. If charging is exited before the
delay expires, the pending one-shot is cancelled and can be retried on a later
charging entry.

During sync, `vars.comms_paused` stops the display's ESP-NOW send/receive loop,
the BLE BMS client is stopped, and the charging screen shows `Wifi time sync`.
The display rebuilds ESP-NOW and restarts BLE before resuming communications;
a rebuild failure releases the pause and resets the display board. If fresh BMS
evidence is not available within 10 seconds after the handoff, the display shows
`charging unknown` and requires a power long-press acknowledgement; it does not
silently report non-charging.

## Timing and safety defaults

### Active transmission and reception timing

The table below is the runtime reference for the current firmware. Reception
cadence is the target interval of the receiving board's processing loop;
expiry is the time without a valid message/send result before the receiver
marks the link stale or applies its safe state. ESP-NOW reception is FIFO: the
firmware drains the available queue and applies the last valid command read.
The motor board keeps the latest display command; the lights board keeps the
latest command separately for each sender (display and motor board).

| Sender → receiver | Information | Send period | Receiver processing / expiry |
| --- | --- | --- | --- |
| Display → motor board | Motor command: `motor_enable`, buttons, lights and relay-off request | 100 ms (10 Hz) | Queue drained every 250 ms; the last valid queued command is applied. If `motor_enable` is absent for 2000 ms, the motor board disables the motors. |
| Motor board → display | System status: battery, current, SOC, speed, temperatures, flags and lights-link health; also repeats the motor-side battery-resistance result | 100 ms (10 Hz) | Processed in the display 250 ms communications loop; the latest queued status is applied. The display marks received motor status stale after 2000 ms. |
| Display → lights board | Rider-light request: low beam, tail and turn signals; excludes the brake bit | Every 250 ms (4 Hz), immediately on state change; failed sends retry with a 50 ms initial interval doubling to a 1000 ms cap | Queue drained every 25 ms; latest display command is applied. Display-owned outputs are reset after 20000 ms without a display message. Display TX health expires after 1500 ms without a successful send. |
| Motor board → lights board | Brake-light state: `REAR_BRAKE_BIT` only | Every 250 ms (4 Hz), immediately on state change; failed sends retry with a 50 ms initial interval doubling to a 1000 ms cap | Queue drained every 25 ms; latest motor command is applied independently of the display command. Motor TX health expires after 1500 ms without a successful send; the brake output is cleared after 2000 ms without a motor heartbeat. |
| Display → power-switch board | Relay command: `turn_off` | Every 250 ms (4 Hz), and once immediately when the state changes | Processed approximately every 20 ms. The display considers its last successful send valid for 1500 ms. |
| Display → power-switch board | Motion/power configuration: threshold, rate, AC mode, timeout and wait period | Only when values change; on send failure, retry every 2000 ms | Processed approximately every 20 ms; valid values are persisted by the power-switch board. |
| Power-switch board → display or motor board | Echo/status of validated power configuration | After a configuration command: 10 frames, 250 ms apart (about 2.25 s total) | Processed by the display communications loop. There is no separate receive-expiry timer for this configuration echo. |
| Lights board → other boards | — | Does not send ESP-NOW frames | Receives and applies commands only. |
| JBD BMS → display | BLE battery current used for local charging detection | Basic/cell queries currently alternate at about 1 Hz | BLE scan uses a 200 ms interval and 30 ms window (about 15% duty cycle), with at most two retries before the BMS is marked unavailable. |

The JBD BMS is never used by the battery-resistance estimator. Motor-side CAN
measurement continues even while the Display is unavailable or showing
`m RX!`; only delivery and presentation of the repeated result are delayed.
The estimator uses the atomic command-`101` voltage/current pair from each
VESC; pending or missing samples do not reset an attempt, and no ESP-NOW
payload change is required.

- Display motor transmission and power communication timeout: 1500 ms.
- Display motor-status receive timeout: 2000 ms.
- Display-to-lights and motor-to-lights TX health timeout: 1500 ms.
- Lights-board motor heartbeat timeout: 2000 ms.
- Power-switch heartbeat: 250 ms.
- Motor-board display-enable timeout: 2000 ms.
- After every disabled-to-enabled transition, the motor board requires the
  throttle to return to zero before applying a motor target.
- The display keeps the normal MAIN screen during the short zero-throttle
  re-arm window after leaving CHARGING; the `MOTOR_BLOCKED` warning is shown
  only when throttle remains active. Rider lights remain available during that
  warning because motor torque and light output have separate safety paths.

### Display button timing

The maintained power button is debounced by `thisButton` and uses a 100 ms
minimum click duration. Durations from 100 ms to below 1000 ms are short clicks;
durations of 1000 ms or more are long presses. Durations below 100 ms are
ignored. The power button's click and long-press callbacks are latched until
the UI task consumes them. The lights input is a maintained switch; its state
is combined with the automatic schedule, with manual ON override as the
default and `auto_lights_schedule_authoritative = True` available for a
schedule-authoritative deployment.

This avoids conflicting writes from multiple firmware modules.

## Migration Phases

Phase 1:

- Keep current direct links working with shared `MSG_COMMAND` and `MSG_STATUS` prefixes.

Phase 2:

- Move lights and power-switch control behind the motor board.
- Add timeout tracking for the links owned by the motor board.

Phase 3:

- Surface health summary and board-specific errors on the display.

Phase 4:

- Remove obsolete direct display-to-lights or display-to-power-switch paths if they are no longer needed.

## Open Questions

No open questions remain for the initial ESPNOW implementation.
