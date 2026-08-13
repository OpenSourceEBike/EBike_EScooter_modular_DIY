# Motor Board

## Role

The motor board is the drive controller and owns motor safety.

It is responsible for:

- receiving rider commands from the display
- controlling the motor drive behavior
- sending the motor-owned rear-brake light bit to the lights board
- reporting system status back to the display

## What it does

Typical motor-board duties include:

- reading brake, throttle, speed, and torque inputs
- computing motor current and speed targets
- sending motor state back to the display
- owning the passive battery-resistance estimator from direct VESC CAN
  voltage/current telemetry
- requesting light state updates when needed
- requesting power-switch actions when needed

## Communication responsibilities

In the active scooter firmware:

- the display sends motor commands directly
- the motor board sends only `REAR_BRAKE_BIT` to the lights board
- the motor board does not communicate with the BMS or report charging state
- the optional JBD BMS is not used for battery-resistance measurement
- the motor board drops drive enable after 2000 ms without a display command
- the motor board performs at most one
  successful measurement per boot and repeats that result in motor status

## Important notes

- The motor board should be the authority for remote-board comms health.
- It should keep last known communication state separately from pending requests.
- It should forward a compact health summary to the display instead of exposing raw link detail unless needed.
- After each disabled-to-enabled transition, throttle release to zero is
  required before a motor target can be applied.
- Battery-resistance configuration must not control the general CAN freshness
  timeout used by speed, current limits, temperatures, voltage, or SOC.
- The feature-local estimator distinguishes pending asynchronous
  `STATUS_4`/`STATUS_5` halves from coherent invalid samples; the motor task
  only passes current VESC snapshots to that module.
- The 20 ms actuation loop sends one target command per VESC and preserves the
  required 3 ms post-send CAN delay. Motor/battery limit refresh runs at 100 ms,
  and CAN receive drains at most 32 already-queued frames without waiting on an
  empty queue.

## Code areas

Relevant code is usually in:

- `01_diy_main_board/escooter/main.py`
- `01_diy_main_board/main.py`
- `common/espnow_protocol.py`

The old `01_diy_main_board/ebike/` path is legacy and not maintained.
