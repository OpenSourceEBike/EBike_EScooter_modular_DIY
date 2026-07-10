# Power-Switch Board

## Role

The power-switch board controls the board or relay path that turns the system on or off.
In this repository, that role is implemented by the automatic power control firmware.

It is responsible for:

- applying power enable or power-off actions
- keeping the hardware power path in a known state

## What it does

Typical power-switch duties include:

- enabling the system when requested
- disabling the system when requested
- confirming receipt of the power request
- helping the system shut down safely

## Communication responsibilities

In the target architecture:

- the motor board sends power-switch requests
- the power-switch board confirms receipt of the request
- the motor board reports failures or timeouts to the display

## Important notes

- The power-switch board should be treated as a stateful hardware endpoint, not just a one-shot command sink.
- If communication stops, the board should preserve a safe power behavior.

## Code areas

Relevant code lives in the automatic power control firmware and the shared ESP-NOW protocol helpers.

- `04_diy_automatic_power_control/main.py`
- `common/espnow_protocol.py`
- `common/espnow.py`
