# Main Board

The main board is the central controller for the drive side of the firmware.
It coordinates motor behavior, reads vehicle inputs, and participates in the ESP-NOW link with the display and other boards.

## Variants

- `01_diy_main_board/escooter/main.py` - active maintained path.
- `01_diy_main_board/ebike/main.py` - legacy path, not maintained.

## Legacy e-bike path

The `ebike/` firmware is kept only as historical reference. It is not aligned
with the current MicroPython ESP-NOW protocol, shared config loader, or active
scooter board topology.

Do not use the e-bike path as the basis for new firmware work unless it is
first migrated to the current shared helpers in `common/`.

## Shared code

The motor board relies on shared helpers from:

- `common/espnow.py`
- `common/espnow_protocol.py`
- `common/config_runtime.py`

## Related docs

- [Motor Board](../docs/boards/motor-board.md)
- [ESP-NOW Architecture Spec](../docs/espnow-architecture-spec.md)
- [Protocol Contract](../docs/protocol-contract.md)
