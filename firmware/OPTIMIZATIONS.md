# ESP32-S3 firmware optimizations

## Scope

This change resolves the three high-priority optimizations from the Python
firmware review. It is constrained to allocation and redraw pressure in the
Motor Board's 20 ms control loop, the Lights Board's 25 ms ESP-NOW receive
loop, and the Display's battery-resistance screens. Protocol payloads,
actuation order, the established 3 ms CAN post-send delay, and safety gates
are unchanged.

## Implemented optimizations

| Area | Change | Rationale |
| --- | --- | --- |
| Motor Board | Replaced per-pass list/generator/`zip` work with explicit rear/front scalar paths. `Throttle.refresh()` updates cached scalar values; the compatibility `value` property remains for other callers. ADC and throttle-to-ERPM scaling use bounded integer arithmetic; CAN Status 1/4/5 and SOC are decoded directly from the received buffer rather than through `struct.unpack_from()` tuples. | At 50 Hz, transient MicroPython objects create regular garbage-collection pressure and timing jitter. The rear/front path preserves each VESC's separate speed limit and prior clamping/dead-zone behavior. |
| Lights Board | The ESP-NOW helper now accepts an output dictionary. Lights allocates it once and clears/refills it per 25 ms receive pass. | An idle receive loop formerly allocated a new dictionary on every iteration. The returned mapping and latest-per-source behavior remain identical. |
| Display resistance views | Dashboard and history widgets cache their input values and call string formatting/widget update only when those values change. Existing LCD/widget dirty tracking then avoids an SPI flush for an unchanged frame. | The UI runs frequently while resistance state normally changes only once per second or per sample. Avoiding duplicate formatting and redraw requests reduces heap churn and bus traffic. |

## Open optimization opportunities

| ID | Priority | Evidence | Recommended next step |
| --- | --- | --- | --- |
| OPT-01 | Medium | `parse_frame()` decodes ASCII, splits it, and builds an integer list for every received ESP-NOW frame. It is used by the 25 ms Lights loop and the Motor/Power receive paths. | Introduce a bounded integer parser that fills a caller-owned fixed buffer, then adapt the decoders without changing the ASCII protocol. Measure radio-burst latency first. |
| OPT-02 | Low | The 100 ms Motor Board current-limit task calls floating-point `map_range()` eight times in dual-motor mode. | Convert only after target measurements confirm it matters; retain the present interpolation semantics or validate any fixed-point rounding at every configuration breakpoint. |
| OPT-03 | Medium | `ui_task()` still invokes the active screen's update/render path every 100 ms. Widget/LCD dirty tracking skips most writes, but screen-level work remains profile-dependent. | Profile each screen on hardware; cache or event-drive only the dominant unchanged screen calculations, preserving warning and safety refresh cadence. |
| OPT-04 | Measurement | The MicroPython CAN driver's `recv()` API creates the received frame object. This is outside the firmware Python layer but can contribute to automatic GC under high CAN traffic. | Measure heap delta and worst-case 20 ms jitter with one/two VESCs. Consider driver-level buffer reuse only if measurements show it is necessary and the patched port supports it. |
| OPT-05 | Low | With EU daylight saving enabled, each Display `date_time()` call recomputes both last-Sunday transition dates using repeated `mktime()` calls. The clock text updates once per second, and the light schedule can request a second conversion in the same pass. | Cache March/October transition days by year, refreshing at a year change; compare boundary behavior before and after on host and measure the target cost before prioritizing. |
| OPT-06 | Low | The Power Board calls `save_power_settings_to_nvs()` on every boot, even when the loaded settings are valid and unchanged; the helper writes five keys and commits. | Persist only when defaults must be installed or values actually change; verify first-boot migration and recovery from invalid NVS values. Measure boot time/flash activity before claiming a gain. |

`OPT-01` through `OPT-06` are optimization work items, not functional or
security issues; they remain separate from `ISSUES.md`.

`OPT-05` references `02_diy_display/rtc_datetime.py:147-177` and
`02_diy_display/escooter/main.py:1195-1203`. `OPT-06` references
`04_diy_automatic_power_control/main.py:152-181` and
`04_diy_automatic_power_control/main.py:296-324`.

## Review update — 2026-09-23

`OPT-05` and `OPT-06` were identified by source review; no target timing or
flash-write measurements were taken. The current host suite passes 57 tests.
The validation below records the earlier implemented optimization change.

## Validation

- `py -3 -m unittest discover -s tests -v`: 53 tests passed.
- `git diff --check`: passed.
- Added host coverage for `Throttle.refresh()` and its backwards-compatible
  tuple property, retained ESP-NOW output-dictionary identity/clearing, and
  unchanged resistance dashboard/history renders.

## Boundaries

The underlying CAN driver's `recv()` API supplies its received frame object;
that allocation is outside this Python layer. This document covers only
allocations and redraw work controlled by this firmware.

## Target validation required before accepting further work

- Measure Motor Board 20 ms worst-case/jitter and heap behavior with one and
  two VESCs under representative CAN traffic.
- Measure Display frame time, heap headroom, and SPI traffic with the
  resistance dashboard and history open.
- Confirm Lights Board ESP-NOW behavior under radio bursts on target hardware.
