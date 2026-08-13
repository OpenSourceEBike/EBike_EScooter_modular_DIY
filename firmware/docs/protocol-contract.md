# ESPNOW Protocol Contract

This page defines the concrete ESPNOW frame shapes used by the current firmware.

## Scope

This contract applies to the board-to-board ESPNOW links used by the firmware.
It covers the display, motor, lights, and automatic power control boards.

## Decisions

These choices match the current implementation:

- Payloads are ASCII numbers separated by spaces.
- Every frame starts with `msg_type, src, dst`.
- Command frames use `MSG_COMMAND, src, dst, ...payload`.
- Status frames use `MSG_STATUS, src, dst, health, ...payload`.
- Frames do not include a sequence field.
- There is no generic acknowledgement frame.
- Board health is inferred from send results, received status frames, timeouts, and board-specific echo/status payloads.
- Lights transmissions use a local retry backoff; this is transport policy and
  does not change the frame shape.

## Message Rules

1. Every ESPNOW message must include a message type.
2. Every ESPNOW message must include a source board ID.
3. Every ESPNOW message must include a target board ID.
4. Every ESPNOW message must be ASCII encoded.
5. Command frames must be `MSG_COMMAND, src, dst, ...payload`.
6. Status frames must be `MSG_STATUS, src, dst, health, ...payload`.

The shared frame contract currently has no generic sequence or acknowledgement
field. Board-specific application acknowledgements must therefore be documented
as separate payload shapes if introduced.

## Constants

Board IDs:

- `BOARD_DISPLAY = 1`
- `BOARD_MOTOR = 2`
- `BOARD_LIGHTS = 3`
- `BOARD_POWER_SWITCH = 4`

Message types:

- `MSG_COMMAND = 1`
- `MSG_STATUS = 2`

Power-switch command IDs:

- `POWER_SWITCH_CMD = 1`
- `POWER_CONFIG_CMD = 2`

Health bits:

- `HEALTH_MOTOR_LIGHTS_TX_OK = 1 << 0`
- `HEALTH_MOTOR_REAR_SPEED_VALID = 1 << 4`

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
`REAR_BRAKE_BIT`. During Wi-Fi time sync, the display light state is not part
of the sync/recovery contract.

The current senders obey that ownership, but the lights receiver still chooses
the ownership path from `mask` instead of enforcing it from `src`. This is kept
for the established runtime behavior and does not change the frame shape.

Display to power-switch relay command:

```text
MSG_COMMAND src dst=BOARD_POWER_SWITCH POWER_SWITCH_CMD turn_off
```

Display to power-switch config command:

```text
MSG_COMMAND src dst=BOARD_POWER_SWITCH POWER_CONFIG_CMD motion_threshold motion_rate_hz motion_ac_mode timeout_seconds wait_seconds
```

Motor to display status:

```text
MSG_STATUS src=BOARD_MOTOR dst=BOARD_DISPLAY health battery_voltage_x10 battery_current_x10 battery_soc_x1000 motor_current_x10 wheel_speed_x10 flags rear_vesc_temp_x10 front_vesc_temp_x10 rear_motor_temp_x10 front_motor_temp_x10 battery_resistance_mohm
```

Status `flags` bit 2 carries `throttle_rearm_required`. Charging state is
detected locally by the display from its BLE BMS connection and is not sent by
the motor board.

### Battery-resistance result

The estimator runs on the motor board. It sends `-1` until the one result for
its boot is available, then repeats the measured `1..2500` mOhm value in every
status. No measurement age, CAN timestamp, or sequence number is added.
Existing Displays continue to ignore the trailing field; a new Display also
accepts the previous 14-field status and treats resistance as unavailable.

The repeated result produces at most one alert per Display boot. An independent
Display reset clears that local latch, so the still-running motor's repeated
result is accepted once and alerts once in the new Display session.

Power-switch to sender config echo/status:

```text
MSG_STATUS src=BOARD_POWER_SWITCH dst health=0 motion_threshold motion_rate_hz motion_ac_mode timeout_seconds wait_seconds
```

## Runtime and safety rules

1. Motor status frames carry the motor-to-lights health bit for display warnings.
2. Power-switch config changes are echoed back as status frames containing the validated values the board accepted.
3. The power-switch board sends the config echo repeatedly after a config change so the sender has multiple chances to receive it.
4. Periodic switch commands can be sent for continuity, while power config commands should be sent only when config values change.
5. The display pauses all ESP-NOW traffic during the charging NTP sync and rebuilds the stack before resuming.
6. The motor board disables drive after a 2000 ms display-command timeout and requires throttle release after re-enable.
7. The lights board clears the motor-owned brake output after 2000 ms without a motor heartbeat.
8. Receivers drain their ESP-NOW queue during each receive cycle and apply only
   the most recent valid command or status for each relevant source. Older
   queued packets are discarded.
9. The display owns the optional BLE BMS connection and local charging
   detection; the motor board does not communicate with the BMS.
10. Failed lights sends retry with an exponential interval starting at 50 ms
    and capped at 1000 ms; successful sends reset the interval.
11. Battery-current (`STATUS_4`), battery-voltage (`STATUS_5`), and speed
    (`STATUS_1`) freshness are tracked independently for each VESC. A
    resistance sample requires a valid voltage/current pair from every
    configured VESC; charging standstill detection requires valid rear speed.
12. The optional JBD BMS is not a battery-resistance source. It remains
    Display-local and is used only by unrelated functions such as charging
    detection.

## Display button contract

The maintained power button uses the shared `thisButton` driver:

- Stable debounce is configured per board (30 ms in the scooter configurations).
- Short click: 100 ms inclusive up to, but not including, 1000 ms.
- Long press: 1000 ms inclusive.
- Presses shorter than 100 ms are ignored.
- Power click and long-press events are latched until the UI task consumes them.

The lights input is a maintained switch, not a momentary click. Its stable
state is combined with the automatic schedule according to
`auto_lights_schedule_authoritative` (manual ON override by default).

## Diagnostics

ESP-NOW diagnostics are controlled by the optional `espnow_debug` runtime
configuration flag, which defaults to `False` in the runtime defaults and all
production board configurations. Persistent transport errors are therefore
quiet in normal operation; enable the flag only during board-local diagnosis.

## Health Rules

1. The display tracks motor TX, motor RX, lights TX, and power-switch TX separately.
2. The motor board reports motor-to-lights TX health through `HEALTH_MOTOR_LIGHTS_TX_OK`.
3. The display turns failed board health into board-specific warning text.
4. Display-to-lights and motor-to-lights TX health expires only after 1500 ms
   without a successful send; an individual lost frame is not a link failure.

## Error Rules

1. Show board-specific warning text.
2. Keep the current warning labels stable: `m TX!`, `m RX!`, `mlTX!`, `l TX!`, and `p TX!`.
3. Keep showing the last known good state when possible.

## Implementation Order

Current implementation priorities:

1. Keep the frame shapes above aligned with `common/espnow_protocol.py`.
2. Keep board-specific command payloads documented when they change.
3. Keep display warning labels aligned with the active health booleans.
