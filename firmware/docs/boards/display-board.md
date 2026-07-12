# Display Board

## Role

The display board is the user-facing controller and UI surface.

It is responsible for:

- reading buttons and user input
- rendering status on screen
- showing warnings and errors
- sending user intent to the rest of the system

## What it does

Typical display features include:

- showing assist level or ride mode
- showing battery and motor status
- showing light state
- showing comms or fault messages
- handling power on and power off requests

## Communication responsibilities

In the active scooter firmware:

- the display sends motor, rider-light, and power-switch commands directly
- the display receives motor status and tracks each remote link separately
- the display schedules the one-shot charging NTP sync after boot

## Important notes

- The display should not own remote hardware state directly.
- It should rely on communication health coming back from the motor board.
- If a board stops replying, the display is the place where the error becomes visible to the rider.
- During NTP sync, `comms_paused` stops all display ESP-NOW traffic until the
  stack has been rebuilt.

## Code areas

Relevant code is usually in:

- `02_diy_display/escooter/main.py`
- `common/espnow_protocol.py`

The old `02_diy_display/ebike/` path is legacy and not maintained.
