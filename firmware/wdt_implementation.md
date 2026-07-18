# Watchdog implementation (historical)

> The active scooter firmware no longer creates or feeds a hardware watchdog.
> The sections below document the former design and are retained for history;
> they are not the current runtime behavior.

## Scope

This document defines the watchdog policy for the active ESP32 firmware
(`escooter` path), including the USB/debug behaviour for the ESP32-C3FN4
boards.

The vehicle is not operated with a USB cable connected. Debugging is therefore
selected explicitly at boot with the BOOT button rather than inferred from USB
presence.

## ESP32-C3 board hardware

The board provides:

- USB-C connector with 5.1 kΩ pull-down resistors on CC1 and CC2;
- 5 V to 3.3 V regulator;
- ESP32-C3FN4;
- native USB on GPIO18 (`D−`) and GPIO19 (`D+`);
- RESET button connected to `CHIP_EN`;
- BOOT button connected to GPIO9;
- blue LED on GPIO8;
- UART on GPIO20 (`RX`) and GPIO21 (`TX`).

The USB data pins and CC resistors do not provide a MicroPython-level,
reliable `host connected` signal. No VBUS-sense GPIO is defined in the current
hardware description. The BOOT button on GPIO9 is therefore the debug
selection mechanism.

## Boot/debug policy

The BOOT button is active low and should be read with an internal pull-up
during `boot.py`, using a short hold window after reset.

When GPIO9 is held low during boot:

- enter `DEBUG/SAFE MODE`;
- do not create the hardware watchdog;
- print a clear `DEBUG MODE: watchdog disabled` message;
- leave the REPL available for PC debugging.

When GPIO9 is not held low:

- start the normal application;
- create the watchdog before starting the main runtime tasks;
- keep feeding it only after the corresponding board work completes
  successfully.

The watchdog cannot be stopped or reconfigured after `machine.WDT(...)` has
started. The BOOT decision must therefore be made before creating the WDT.

## Feed point by board

| Board | Current watchdog | Recommended feed point | Why |
| --- | --- | --- | --- |
| Motor board | 30 s, created in `01_diy_main_board/escooter/main.py` | At the end of `task_control_motor()`, after throttle safety, display-enable timeout, brake handling and motor CAN commands complete | This is the safety-critical control task. If it stops, the watchdog must reset the board. The existing feed at this point is appropriate. |
| Display board | 30 s, created in `02_diy_display/escooter/main.py` | At the end of `main_task()`, after button processing, shutdown decisions and control-state updates; retain the feed in `power_off_forever()` | The normal control task proves that the UI/control loop is alive. The power-off loop must continue feeding while it deliberately waits for the physical power-button transition. |
| Lights board | Not currently implemented | Add a watchdog and feed once per completed 25 ms main-loop iteration, after ESP-NOW receive, timeout enforcement and GPIO output update | A stuck lights loop must reset to recover communications. After reset, all output pins are initialized off before normal processing. |
| Power-control board | Not currently implemented | Add a watchdog and feed only after ESP-NOW command processing, motion/accelerometer processing, relay timeout evaluation and relay-output decisions complete | This is the most important missing watchdog. A lock-up must not leave the relay path asserted indefinitely. The relay pins must be driven to the safe state before or as part of reset recovery. |

## Feed rules

`wdt.feed()` must not run from an independent timer task that can continue
while the real control task is blocked. Feeding is evidence that the board's
critical work completed, not merely that the scheduler is running.

The feed should occur after:

1. input and communication processing;
2. safety timeout checks;
3. actuator/output decisions;
4. error checks for the current cycle.

If any of these steps raises an exception or blocks indefinitely, the watchdog
must be allowed to expire. A broad exception handler must not feed the WDT
after a failed cycle.

## Timeouts and test values

The current 30-second timeout is suitable as a recovery backstop but is long
for a vehicle controller. Before reducing it, measure the worst-case duration
of CAN, BLE, Wi-Fi/NTP, ESP-NOW and garbage-collection operations on hardware.

Recommended validation tests:

- hold BOOT during reset and confirm no watchdog reset occurs in the REPL;
- release BOOT and confirm the normal watchdog starts;
- deliberately stop the feed and verify reset time and reset cause;
- block each critical loop independently and verify actuator safe state;
- disconnect/reconnect USB and confirm USB presence does not change watchdog
  policy;
- verify the power-board relay state after watchdog reset.

## Important limitation

The BOOT button is a deliberate debug override. It must not be treated as a
vehicle-running mode. With BOOT held, motor/relay safety firmware may not be
running at all; use this mode only with the vehicle mechanically safe and
power isolated as appropriate.
