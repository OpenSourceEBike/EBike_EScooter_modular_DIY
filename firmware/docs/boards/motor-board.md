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
- Battery-resistance configuration must not control the CAN freshness timeouts
  used by speed, current limits, temperatures, voltage, or SOC.
- VESC `STATUS_1`, `STATUS_4`, and `STATUS_5` are expected at 10 Hz and use
  the 500 ms freshness timeout. The VESC LISP helper sends project-private
  command `100` SOC at 1 Hz and command `101` precision voltage/current at
  10 Hz; SOC stays valid for 30000 ms and command `101` is used only by the
  estimator. Command `101` is an eight-byte big-endian payload: unsigned
  32-bit mV followed by signed 32-bit mA.
- The estimator accepts only fresh, atomic command-`101` mV/mA samples from
  every VESC, with a bounded rear/front receipt-time skew. Standard status
  frames remain independent operational telemetry.
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
