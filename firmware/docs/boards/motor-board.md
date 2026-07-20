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
- requesting light state updates when needed
- requesting power-switch actions when needed

## Communication responsibilities

In the active scooter firmware:

- the display sends motor commands directly
- the motor board sends only `REAR_BRAKE_BIT` to the lights board
- the motor board does not communicate with the BMS or report charging state
- the motor board drops drive enable after 2000 ms without a display command

## Important notes

- The motor board should be the authority for remote-board comms health.
- It should keep last known communication state separately from pending requests.
- It should forward a compact health summary to the display instead of exposing raw link detail unless needed.
- After each disabled-to-enabled transition, throttle release to zero is
  required before a motor target can be applied.

## Code areas

Relevant code is usually in:

- `01_diy_main_board/escooter/main.py`
- `01_diy_main_board/main.py`
- `common/espnow_protocol.py`

The old `01_diy_main_board/ebike/` path is legacy and not maintained.
