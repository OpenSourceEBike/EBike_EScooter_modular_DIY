# ESP32-S3 firmware optimizations

## Scope

This document records completed and open performance work in the maintained
scooter firmware. The 2026-10-05 review covers the Motor, Display, Lights and
Power boards, shared radio helpers, and the active JBD BMS charging path.
Target timing and heap measurements are still required before changing
control-loop behavior.

## Implemented optimizations

| Area | Change | Rationale |
| --- | --- | --- |
| Motor Board | Replaced per-pass list/generator/`zip` work with explicit rear/front scalar paths. `Throttle.refresh()` updates cached scalar values; the compatibility `value` property remains for other callers. ADC and throttle-to-ERPM scaling use bounded integer arithmetic; CAN Status 1/4/5 and SOC are decoded directly from the received buffer rather than through `struct.unpack_from()` tuples. | At 50 Hz, transient MicroPython objects create regular garbage-collection pressure and timing jitter. The rear/front path preserves each VESC's separate speed limit and prior clamping/dead-zone behavior. |
| Lights Board | The ESP-NOW helper now accepts an output dictionary. Lights allocates it once and clears/refills it per 25 ms receive pass. | An idle receive loop formerly allocated a new dictionary on every iteration. The returned mapping and latest-per-source behavior remain identical. |

## Open optimization opportunities

| ID | Priority | Evidence | Recommended next step |
| --- | --- | --- | --- |
| OPT-01 | Medium | `parse_frame()` decodes ASCII, splits it, and builds an integer list for every received ESP-NOW frame. It is used by the 25 ms Lights loop and the Motor/Power receive paths. | Introduce a bounded integer parser that fills a caller-owned fixed buffer, then adapt the decoders without changing the ASCII protocol. Measure radio-burst latency first. |
| OPT-02 | Low | The 100 ms Motor Board current-limit task calls floating-point `map_range()` eight times in dual-motor mode. | Convert only after target measurements confirm it matters; retain the present interpolation semantics or validate any fixed-point rounding at every configuration breakpoint. |
| OPT-03 | Medium | `ui_task()` still invokes the active screen's update/render path every 100 ms. Widget/LCD dirty tracking skips most writes, but screen-level work remains profile-dependent. | Profile each screen on hardware; cache or event-drive only the dominant unchanged screen calculations, preserving warning and safety refresh cadence. |
| OPT-04 | Measurement | The MicroPython CAN driver's `recv()` API creates the received frame object. This is outside the firmware Python layer but can contribute to automatic GC under high CAN traffic. | Measure heap delta and worst-case 20 ms jitter with one/two VESCs. Consider driver-level buffer reuse only if measurements show it is necessary and the patched port supports it. |
| OPT-05 | Low | With EU daylight saving enabled, each Display `date_time()` call recomputes both last-Sunday transition dates using repeated `mktime()` calls. The clock text updates once per second, and the light schedule can request a second conversion in the same pass. | Cache March/October transition days by year, refreshing at a year change; compare boundary behavior before and after on host and measure the target cost before prioritizing. |
| OPT-06 | Low | The Power Board calls `save_power_settings_to_nvs()` on every boot, even when the loaded settings are valid and unchanged; the helper writes five keys and commits. | Persist only when defaults must be installed or values actually change; verify first-boot migration and recovery from invalid NVS values. Measure boot time/flash activity before claiming a gain. |
| OPT-07 | Medium | The Display configures the JBD client with `interleave_cells=True`, so every other BLE query requests cell voltages. The active charging path reads only BASIC pack voltage/current; no production caller reads the cell getter. | Consider BASIC-only polling for the maintained scooter profile. Compare fresh-current latency, BLE/ESP-NOW coexistence and BMS behavior on hardware before changing the query mix. |
| OPT-08 | Medium | Motor and Display receive paths call `espnow_recv_all()`, which builds a list containing up to 32 `(host, msg)` tuples on each pass. The parsers then allocate decoded integer lists. | Add a bounded streaming receive helper that lets callers retain only the latest relevant packet. Measure heap churn and receive latency during bursts; preserve packet order and timeout behavior. |
| OPT-09 | Low | `Mode.tick()` reads each throttle through the compatibility `value` property every 100 ms, which performs another ADC read and builds a tuple after the 20 ms motor task has already refreshed the same throttles. | Reuse a recent cached scaled value or a shared snapshot once the freshness and mode-change behavior are verified. Measure the benefit before changing input timing. |

These are optimization work items; functional and safety findings are tracked
in `ISSUES.md`. In particular, OPT-07 should be considered together with
CHG-01, which concerns the correctness of charging detection.

**Code references:** OPT-05: `02_diy_display/rtc_datetime.py` and
`02_diy_display/escooter/main.py:1028-1036`; OPT-06:
`04_diy_automatic_power_control/main.py:152-181` and `:296-324`;
OPT-07: `02_diy_display/escooter/main.py:242-283` and
`02_diy_display/bms_jbd.py:236-244`; OPT-08: `common/espnow.py:88-104`,
`01_diy_main_board/escooter/main.py:398-433`, and
`02_diy_display/escooter/main.py:1134-1168`; OPT-09:
`01_diy_main_board/mode.py:44-67` and
`01_diy_main_board/throttle.py:25-38`.

## Review update — 2026-10-05

OPT-07 through OPT-09 are based on source inspection; no target radio, heap,
ADC or timing measurements were taken. The current host suite passed 37 tests,
and `bash -n scripts/update_firmware.sh` passed. Existing host coverage checks
`Throttle.refresh()` and ESP-NOW receive bounds, but does not establish the
performance benefit of these proposals.

## Boundaries

The underlying CAN driver's `recv()` API supplies its received frame object;
that allocation is outside this Python layer. This document covers only
allocations and redraw work controlled by this firmware.

## Target validation required before accepting further work

- Measure Motor Board 20 ms worst-case/jitter and heap behavior with one and
  two VESCs under representative CAN traffic.
- Confirm Lights Board ESP-NOW behavior under radio bursts on target hardware.
