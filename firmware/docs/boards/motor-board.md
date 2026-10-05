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
- After each disabled-to-enabled transition, throttle release inside the zero
  deadband for 100 continuous milliseconds is required before a motor target
  can be applied.
- VESC standard Status 1, 4 and 5 at 10 Hz provide ERPM/motor current,
  temperatures/input current, and pack voltage respectively. All three CAN
  statuses use a 2000 ms freshness timeout.
- The rear VESC LispBM helper sends only SOC x1000 as project-private command
  `99`, once per second. Rear SOC remains authoritative and uses the same
  2000 ms CAN freshness timeout. Front SOC is ignored.
- Status-4 temperatures outside -50.0..200.0 C are published as unavailable
  (`-2550`). Rear ERPM is the primary speed source; fresh front ERPM is a
  Display-only fallback. Normal battery status combines fresh Status-4/5
  branches using absolute-current-weighted voltage and summed signed current.
- The 20 ms actuation loop sends one target command per VESC and preserves the
  required 3 ms post-send CAN delay. Motor/battery limit refresh runs at 100 ms,
  CAN receive drains at most 32 already-queued frames every 20 ms without
  waiting on an empty queue.

## Code areas

Relevant code is usually in:

- `01_diy_main_board/escooter/main.py`
- `01_diy_main_board/main.py`
- `common/espnow_protocol.py`

The old `01_diy_main_board/ebike/` path is legacy and not maintained.
