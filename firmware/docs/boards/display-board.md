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
  calculated by the motor board

## Communication responsibilities

In the active scooter firmware:

- the display sends motor, rider-light, and power-switch commands directly
- the display receives motor status and tracks each remote link separately
- the display owns the optional BLE BMS connection and `battery_is_charging`
- the optional BMS is not used for battery-resistance measurement
- the display schedules the one-shot charging NTP sync after boot

## Important notes

- The display should not own remote hardware state directly.
- It should rely on communication health coming back from the motor board.
- If a board stops replying, the display is the place where the error becomes visible to the rider.
- During NTP sync, `comms_paused` stops all display ESP-NOW traffic until the
  stack has been rebuilt. The BLE BMS client is also stopped and restarted so
  it does not contend with Wi-Fi during synchronization.
- The resistance flow latches the first valid repeated motor result per
  Display boot. Its timestamp is Display receipt time, or `na` without RTC;
  no measurement age is transported.
- Consequently, repeated frames alert only once during a normal Display boot.
  If only the Display resets while the motor stays powered, the new session
  accepts the repeated result once and alerts once again.

## Code areas

Relevant code is usually in:

- `02_diy_display/escooter/main.py`
- `02_diy_display/bms_jbd.py`
- `common/espnow_protocol.py`

The old `02_diy_display/ebike/` path is legacy and not maintained.
