# Firmware remediation log — 2026-09-21

## Scope

This change set resolves `BMS-06`, `BMS-07`, `BMS-08`, `DEP-01`, and
`RTC-01` from the firmware review. It is limited to the maintained scooter
firmware, the incremental updater, related documentation, and host regression
tests.

No ESP-NOW/CAN payload was changed. Manual single-VESC
`resistance-peer-enabled` behavior, the normal `Ready`/`BOOT`/power gate, and
the replacement of only `MAIN` by the battery-resistance dashboard are
unchanged.

## Change summary

| Issue | Implemented change | Rationale |
| --- | --- | --- |
| `BMS-06` | Clear cached JBD measurements and the receive buffer on every lifecycle reset, connection failure, and new BLE connection. | Data acquired under one BLE connection must never remain accessible, be completed, or be timestamped as telemetry from a later connection. |
| `BMS-07` | Queue every completed resistance result and persist it immediately; retry failures every 5 seconds and once more during explicit shutdown. | The independent Power Board can remove Display power before the former shutdown-only save path runs. A per-result queue also prevents several measurements being collapsed into one history row. |
| `BMS-08` | Parse the JBD one-byte payload length, require success status and an exact frame length, and accept only the checksum over status, length, and payload. | Alternate checksum windows made structurally invalid or corrupted frames look valid. The parser now implements one unambiguous JBD response contract. |
| `DEP-01` | Compare the complete previous per-board manifest with the new manifest and remove every path that disappeared, including a previously selected configuration file. | A board update must converge to the selected firmware set instead of accumulating renamed, deleted, or old configuration modules. |
| `RTC-01` | Remove explicit Wi-Fi scanning from the production async path, replace blocking sleeps with `uasyncio.sleep_ms()`, and perform DNS plus NTP over non-blocking UDP under one deadline. | Charging-time clock synchronization runs in the Display scheduler; synchronous scan, sleep, DNS, or NTP calls could stall UI and communication tasks. |

## Detailed implementation

### JBD session and frame integrity (`BMS-06`, `BMS-08`)

`02_diy_display/bms_jbd.py` now treats cached measurements and the receive
buffer as connection-scoped state. `start()`, `stop()`, unavailable-client
recovery, connection failure, and the BLE connect event all discard prior data.
This covers a previously parsed value, a complete old frame waiting to be
drained, and a partial frame that could otherwise be joined to notifications
from the next connection.

The response parser now applies these checks before exposing a BASIC frame:

1. start byte `0xDD` and terminator `0x77`;
2. success status byte equal to zero;
3. total size exactly `7 + payload_length`;
4. checksum exactly equal to the two's complement of the sum of status,
   payload length, and payload bytes.

The former seven alternative checksum intervals are no longer accepted.

### Durable resistance results (`BMS-07`)

`02_diy_display/escooter/main.py`, `02_diy_display/vars.py`, and
`common/battery_resistance_persistence.py` now implement a small persistence
transaction:

- a completed measurement is added to a FIFO queue;
- the history row is appended immediately;
- a record is removed from RAM only after its append succeeds;
- the summary is then published with the existing atomic temporary-file flow;
- failures stay marked as dirty and are retried every 5 seconds;
- explicit shutdown remains the final flush path.

The queue is bounded at 16 records. When full, the firmware first retries the
existing work; if storage is still unavailable, it rejects the new result and
logs the condition instead of allowing unbounded RAM growth. This protects the
normal automatic-power-cut scenario, but cannot guarantee persistence during a
permanent flash failure or a power loss while records are still queued.

History remains authoritative during startup recovery. If power is lost after
the CSV append but before summary publication, the existing history scan
reconstructs the last/minimum/maximum summary.

### Incremental deployment cleanup (`DEP-01`)

`scripts/update_firmware.sh` builds a set of all paths in the new deployment
and compares it with the board's previous manifest. Every old-only path is
removed, not just the hard-coded legacy list. This includes the configuration
module left behind when the updater is run with a different `config_*.py`.

Only simple absolute device paths already owned by that board's manifest are
eligible for removal. An unsafe path or failed deletion aborts the operation;
the replacement manifest is published and the board is reset only after all
uploads and removals succeed.

### Cooperative Wi-Fi/NTP synchronization (`RTC-01`)

The asynchronous Display path no longer calls the synchronous WLAN scan or
`ntptime.settime()`. Station reset delays yield to the scheduler. Hostname
resolution uses a minimal DNS A query sent to the DHCP-provided DNS server,
then NTP uses a non-blocking UDP socket. DNS and NTP share one hard timeout, so
DNS cannot consume a full timeout and then start another unrestricted wait.

The response is accepted only when it is a complete NTP packet in server or
broadcast mode with nonzero stratum. The decoded UTC value is written through
the new `RTCDateTime.set_internal_utc()` method; the existing local-time and
external-RTC handling remains unchanged. The separate synchronous API is kept
for callers that explicitly choose a blocking call, but it is not used by the
charging-time production task.

## Files changed

- `02_diy_display/bms_jbd.py`
- `02_diy_display/escooter/main.py`
- `02_diy_display/rtc_datetime.py`
- `02_diy_display/vars.py`
- `02_diy_display/wifi_time_sync.py`
- `common/battery_resistance_persistence.py`
- `scripts/update_firmware.sh`
- `tests/test_bms_jbd_recovery.py`
- `tests/test_bms_battery_resistance_persistence.py`
- `tests/test_wifi_time_sync.py`
- `README.md`
- `docs/battery-resistance-measurement.md`
- `docs/espnow-architecture-spec.md`
- `ISSUES.md`

## Validation

- `py -3 -m unittest discover -s tests -v`: 47 tests passed.
- Python syntax compilation: all 95 Python files present in the checkout
  compiled successfully.
- `bash -n scripts/update_firmware.sh`: passed.
- `git diff --check`: passed.

New regression coverage verifies disposal of cached/complete/partial JBD data,
declared-length, canonical-checksum and status enforcement, non-coalesced queued
resistance rows, retry retention after an append failure, duplicate prevention
after a summary write failure, DNS parsing, NTP epoch conversion, removal of
the blocking calls from the asynchronous path, and a successful asynchronous
NTP-to-internal-RTC update using one shared deadline.

## Hardware validation still required

The host checks do not replace these target tests:

- disconnect/reconnect a real JBD BMS during partial and complete BASIC frames;
- force an actual Display filesystem write failure and cut relay power during
  the retry window;
- run the updater against each board, including a configuration switch and a
  deleted/renamed managed file;
- verify DNS/NTP against the deployed router and NTP host while observing UI,
  BLE restart, ESP-NOW recovery, heap use, and scheduler latency.

Only the Display must be reflashed for the JBD, persistence, and RTC runtime
changes. The updater change runs on the maintenance host. No Motor Board
protocol change is required by this remediation.
