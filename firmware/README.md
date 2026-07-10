# Firmware Wiki

This folder is the entry point for the firmware docs.

## Boards

The firmware is split across a few cooperating boards and runtime targets:

- Display board: the rider interface, screen, and button handling.
- Motor board: the drive controller and system coordinator.
- Lights board: the board that drives headlights, tail lights, and turn signals.
- Power-switch board: the board that handles power enable and shutoff behavior. This is implemented in the automatic power control firmware.

Each board has its own page:

- [Display Board](./docs/boards/display-board.md)
- [Motor Board](./docs/boards/motor-board.md)
- [Lights Board](./docs/boards/lights-board.md)
- [Power-Switch Board](./docs/boards/power-switch-board.md)

## ESPNOW

The boards communicate over ESPNOW.
The intended board-to-board flow is documented here:

- [ESP-NOW Architecture Spec](./docs/espnow-architecture-spec.md)
- [Protocol Contract](./docs/protocol-contract.md)
- [Documentation Organization](./docs/documentation-organization.md)

## What this wiki is for

- Explain what each board does.
- Describe how the boards communicate.
- Capture the intended ESPNOW ownership model before code changes.
- Make it easier to update the firmware without re-learning the system every time.

## Code Layout

The main firmware entry points live here:

- `01_diy_main_board/` - motor board firmware. The active maintained path is `escooter/`; `ebike/` is legacy and not maintained.
- `02_diy_display/` - display board firmware and UI code. The active maintained path is `escooter/`; `ebike/` is legacy and not maintained.
- `03_diy_lights_board/` - lights board firmware.
- `04_diy_automatic_power_control/` - power-switch / automatic power control firmware.
- `common/` - shared protocol, config, and utility code.

## Deployment

The firmware boot loader expects exactly one `config_*.py` file at the repository root on the device.

When flashing or copying the repo to a board:

- Keep only the single config file that matches the target build.
- Remove or rename every other `config_*.py` file before boot.
- If you want to keep multiple configs in the checkout for development, keep them in the source tree on your computer, but deploy only one of them to the device root.

This is the convention enforced by `common/config_runtime.py`.

## Suggested reading order

1. Read the board introductions above.
2. Read the board pages you are changing.
3. Read the ESP-NOW architecture spec.
4. Update the spec if the design changes.
