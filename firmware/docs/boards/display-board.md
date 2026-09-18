# Display Board

## Role

The display board is the user-facing controller and UI surface.

It is responsible for:

- reading buttons and user input
- rendering status on screen
- showing warnings and errors
- sending user intent to the rest of the system
- reading the optional JBD BMS over BLE and detecting charging locally

## What it does

Typical display features include:

- showing assist level or ride mode
- showing battery and motor status
- showing light state
- showing comms or fault messages
- handling power on and power off requests
- presenting, timestamping, and persisting the battery-resistance result
  estimated locally from JBD BMS Bluetooth BASIC frames

## Communication responsibilities

In the active scooter firmware:

- the display sends motor, rider-light, and power-switch commands directly
- the display receives motor status and tracks each remote link separately
- the display owns the optional BLE BMS connection and `battery_is_charging`
- the JBD BMS is the only source used for the passive battery-resistance
  estimator
- the display schedules one charging NTP sync per boot; after it starts, later
  charging-state changes cannot schedule another one

## Important notes

- The display should not own remote hardware state directly.
- It should rely on communication health coming back from the motor board.
- If a board stops replying, the display is the place where the error becomes visible to the rider.
- During NTP sync, `comms_paused` stops all display ESP-NOW traffic until the
  stack has been rebuilt. The BLE BMS client is also stopped and restarted so
  it does not contend with Wi-Fi during synchronization.
- The resistance flow accepts only unique fresh BMS BASIC timestamps. It
  captures three reference samples inside -250 W to +250 W, waits through one
  settling frame after a 750 W discharge event, then averages three load
  samples at or below -750 W. A completed result is held
  until a reference-power sample returns, avoiding repeated alerts during one
  load event.

## Code areas

Relevant code is usually in:

- `02_diy_display/escooter/main.py`
- `02_diy_display/bms_jbd.py`
- `common/espnow_protocol.py`

The old `02_diy_display/ebike/` path is legacy and not maintained.
