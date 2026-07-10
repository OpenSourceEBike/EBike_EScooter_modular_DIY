# Motor Board

## Role

The motor board is the system coordinator for drive-related logic and the ESP-NOW hub in the target design.

It is responsible for:

- receiving rider commands from the display
- controlling the motor drive behavior
- tracking board health for remote devices
- forwarding requests to lights and power-switch boards
- reporting system status back to the display

## What it does

Typical motor-board duties include:

- reading brake, throttle, speed, and torque inputs
- computing motor current and speed targets
- sending motor state back to the display
- requesting light state updates when needed
- requesting power-switch actions when needed

## Communication responsibilities

In the target architecture:

- the display talks only to the motor board
- the motor board talks to the lights board and power-switch board
- the motor board owns retries, receive confirmations, and timeouts for those links

## Important notes

- The motor board should be the authority for remote-board comms health.
- It should keep last known communication state separately from pending requests.
- It should forward a compact health summary to the display instead of exposing raw link detail unless needed.

## Code areas

Relevant code is usually in:

- `01_diy_main_board/escooter/main.py`
- `01_diy_main_board/main.py`
- `common/espnow_protocol.py`

The old `01_diy_main_board/ebike/` path is legacy and not maintained.
