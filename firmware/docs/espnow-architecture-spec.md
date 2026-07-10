# ESPNOW Architecture Spec

> Wiki entry point: [Firmware Wiki](../README.md)

## Purpose

This document defines the intended ESPNOW communication architecture for the firmware before any code changes are made.

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

## Target Topology

The target design is a hub-and-spoke model:

- Display board is the UI and user input source.
- Motor board is the ESPNOW coordinator.
- Lights board and power-switch board are managed through the motor board.

Target communication rules:

- Display talks only to the motor board.
- Motor board talks to the lights board and power-switch board.
- Motor board forwards a summarized health/state view to the display.

## Board Responsibilities

### Display board

- Collects user input.
- Renders status and errors.
- Sends user intent to the motor board.
- Receives board health and system state from the motor board.

### Motor board

- Owns ESPNOW routing for all non-display boards.
- Translates display intent into board-specific requests.
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

## Current Frame Shapes

Display to motor command:

```text
MSG_COMMAND src=BOARD_DISPLAY dst=BOARD_MOTOR motor_enable buttons lights turn_off
```

Display or motor to lights command:

```text
MSG_COMMAND src dst=BOARD_LIGHTS mask state
```

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
MSG_STATUS src=BOARD_MOTOR dst=BOARD_DISPLAY health battery_voltage_x10 battery_current_x10 battery_soc_x1000 motor_current_x10 wheel_speed_x10 flags rear_vesc_temp_x10 front_vesc_temp_x10 rear_motor_temp_x10 front_motor_temp_x10
```

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

- Lights state: motor board owns the request flow and health tracking; lights board owns the output pins.
- Power-off state: motor board owns the request flow and health tracking; power-switch board owns the relay state.
- Motor/display link: motor board owns the state relay and health summary for the display.

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
