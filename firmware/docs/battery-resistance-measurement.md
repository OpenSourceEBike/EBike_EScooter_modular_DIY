# Battery Resistance Measurement

## Status and purpose

This page defines the implemented algorithm and board ownership for the
battery-resistance feature.

The firmware shall estimate and retain one comparable battery DC resistance
value per motor-board boot from normal riding loads. It must not command a load
step, enable a motor, change current limits, or otherwise alter riding behaviour
to obtain a measurement.

The value is an effective pack-path resistance. It can include cells, BMS,
fuse, connectors, cabling, and controller measurement error; it is not a
laboratory cell-only impedance measurement.

## Ownership and data flow

The motor board owns the estimator because it receives VESC CAN telemetry
directly. Intermittent Display communication, including `m RX!`, must not affect
an attempt already running on the motor board.

The calculation uses a project-private VESC LISP CAN frame (command `101`):

- each VESC sends its filtered input voltage as unsigned 32-bit mV and input
  current as signed 32-bit mA in the same eight-byte frame at 10 Hz;
- the motor board timestamps receipt of that atomic pair;
- every configured VESC must have a fresh valid precision pair;
- in dual-motor mode, rear/front receipt timestamps must be close enough to
  represent the same load.

The same atomic `101` pair is also preferred for normal battery voltage/current
telemetry while it is fresh. It remains the estimator input, so its precision
and atomic delivery are not reduced for presentation.

The optional JBD BMS is never an input to this calculation. It remains available
for unrelated Display functions such as charging detection. The optional RTC is
also not involved in the calculation.

After a successful measurement, the motor board repeats the result in every
periodic motor-status frame. The Display latches the first valid result received
during its boot, updates last/min/max in RAM, shows the alert, and later writes
history during explicit shutdown. Radio loss can delay delivery but cannot
change the measured value.

No measurement timestamp, measurement age, CAN timestamp, or sequence number
is transported. If the Display RTC is valid, the stored timestamp is the first
receipt time at the Display; otherwise it is `na`.

## Dual-motor aggregation

Battery currents are discharge-positive and are summed:

```text
Itotal = Irear + Ifront
```

The equivalent voltage is weighted by the absolute branch currents, so a
controller carrying little or no current does not receive equal weight and
opposite current signs cannot move the result outside the measured branch
voltages:

```text
W = abs(Irear) + abs(Ifront)
Vequiv = (Vrear * abs(Irear) + Vfront * abs(Ifront)) / W
```

If all branch currents are zero, `Vequiv` is the arithmetic mean of their
voltages. `Itotal` remains the signed sum used for battery power and resistance.

For a single-motor configuration, `Itotal` and `Vequiv` are simply that VESC's
values. Signed current is preserved so regeneration can be used while acquiring
the reference. Non-positive voltage on any configured branch, a stale pair, or
excessive rear/front timestamp skew makes the aggregate sample invalid.

## Measurement conditions

All timing uses monotonic `ticks_ms()` arithmetic on the motor board.

### State machine

| ID | State | Conditions | Required time/samples | Success | Failure or wait |
| --- | --- | --- | --- | --- | --- |
| 0 | `get reference` | Power between -100 W and +100 W inclusive. | 10 continuous seconds; retain latest five valid samples. | Freeze the trimmed reference and go to `ramp to load`. | Any value outside the window discards the incomplete reference and restarts. |
| 1 | `ramp to load` | Power exceeded +100 W. | Reach 750 W within 3 s. | At `>=750 W`, go to `get load`. | Falling back or exceeding 3 s fails the attempt. |
| 2 | `get load` | Power at least 750 W. | 15 continuous seconds. | Go to `collect samples`. | Power below 750 W, a missed second, or invalid input fails the attempt. |
| 3 | `collect samples` | Power at least 750 W. | Five valid samples within one second. | Trim min/max, average the middle three, then complete. | Timeout or invalid/low power fails the attempt. |
| 4 | `complete` | A valid result was published. | One result per boot. | Remain complete. | Next boot only. |
| 5 | `failed` | 25 attempts failed. | Terminal for this boot. | None. | Next boot only. |

There are at most 25 attempts in total, including the first one. An attempt
begins only when `get load` receives its first sample at or above 750 W. Filling
the rolling reference and the 3-second ramp do not increment the
attempt counter.

### 1. `get reference`

Reference collection starts immediately after boot:

```text
reference_power_min_w = -100
reference_power_max_w = 100
reference_qualify_ms = 10000
```

While aggregate battery power is between -100 W and +100 W inclusive, keep a rolling buffer of
the latest five valid aggregate pairs. Consecutive valid telemetry observations
may all enter the buffer. Negative and zero power are valid. After 10 continuous
seconds, freeze the buffer. Sort voltage and current independently,
discard each minimum and maximum, and average each set of three remaining
values:

```text
Vref = mean(sorted(Vref_samples)[1:4])
Iref = mean(sorted(Iref_samples)[1:4])
```

If power leaves the window before 10 seconds, the incomplete reference is
discarded and timing restarts. A frozen reference has
no maximum age while waiting for load.

### 2. `get load`

Starting at the first aggregate sample with `Vequiv * Itotal >= 750 W`, require
20 continuous seconds of observed load. The only power condition in this state
is:

- every observed aggregate power is at least 750 W;

Every elapsed second still needs an observation from which aggregate power can
be measured. Regeneration flags and individual signed currents do not impose an
additional condition when aggregate power is at least 750 W.

A failure returns to `get reference` and clears the previous reference. After
the 25th failed load attempt, the estimator enters terminal state `failed` and
does not try again until the motor board restarts.

During temporary field diagnosis, the Display `MAIN` screen is replaced by a
five-line resistance status view. This makes the live estimator phase and its
rolling sample progress visible while riding; it does not change motor control
or command a measurement load. The normal resistance-history screen remains
available from the manual charging-screen flow. Normal riding indicators and
warnings are intentionally omitted from this temporary diagnostic view.

The five lines show estimator state, phase progress, signed live battery power,
sample/result progress, and `retries`. Live power uses the Display's fresh motor
status voltage/current pair and is formatted with an explicit sign; it shows
`power: na` while motor-board status is not fresh. The former CAN loss/status
line is deliberately omitted to keep `retries` visible.

Continuity means that every elapsed second has at least one valid observation.
One valid observation in that second is sufficient; the firmware does not
attempt to reconstruct current changes inside CAN frames that were never
received.

### Precision input tracking

`BatteryResistanceEstimator` owns the variable-interval tracker inside
`common/battery_resistance.py`. It observes each VESC's command-`101` update
counter, atomic raw pair, and motor-board receipt timestamp and classifies a
snapshot as:

- pending: one VESC pair is missing, stale, or temporarily over-skew; preserve
  the attempt until the active phase misses a required elapsed second;
- invalid: malformed values, impossible timestamps, non-positive voltage, or a
  coherent invalid aggregate; cancel only the current attempt. Signed current
  and the regen flag do not independently reject an otherwise measurable pair;
- valid: all configured VESC pairs and rear/front timestamps are coherent;
  advance the monitor.

The motor entry point makes one feature call per 50 ms refresh cycle. The
source frame is VESC-local and no synchronised LISP clock is assumed.

### 3. Last five load samples

During the 20-second qualification window, accept valid aggregate samples
subject to:

- the same power and freshness rules;
- no additional minimum interval between samples;
- keep only the last five accepted samples in the qualification window.

Examples:

- the rolling window follows the actual source-update cadence; with two 10 Hz
  VESC streams staggered in time, five consecutive aggregate observations can
  cover only approximately the final quarter-second of qualification;
- if fewer than five valid samples are accepted by qualification end, reset
  the attempt and collect a new reference.

An observation enters the rolling buffer only after it produces a plausible
resistance value. An observation with no positive voltage drop, no positive
current step, or an out-of-range result does not prevent the immediately next
valid observation from being used.

For every accepted sample:

```text
R_mOhm = 1000 * (Vref - Vsample) / (Isample - Iref)
```

The current must be above the reference current and the voltage drop must be
positive. Each result must be in the inclusive configured range:

```text
1 <= R_mOhm <= 2500
```

Sort the last five resistance samples, discard the minimum and maximum, and use
the integer mean of the remaining three as the final result. This trimmed mean
prevents either extreme from dominating the one-result-per-boot measurement.

## Configuration contract

`common/config_battery_resistance.py` contains the shared settings. Ownership
and validation are split:

- the motor board validates power thresholds, the fixed total attempt limit,
  freshness/skew, fixed qualification duration, sample count,
  and resistance range;
- the Display validates only accepted result range, alert duration, filenames,
  and history size.

An invalid motor-side setting disables only the estimator and leaves general
CAN expiry/safety behaviour unchanged. An invalid Display persistence/UI setting
must not disable motor-side measurement or abort Display boot.

Implemented sampling settings:

```text
reference_power_min_w = -100
reference_power_max_w = 100
reference_qualify_ms = 10000
load_power_min_w = 750
load_transition_timeout_ms = 3000
load_qualify_ms = 15000
sample_collection_timeout_ms = 1000
max_attempts = 25
sample_count = 5
vesc_precision_sample_max_age_ms = 1500
dual_vesc_precision_max_skew_ms = 250
min_mohm = 1
max_mohm = 2500
```

## Motor-status result transport

The implementation preserves the meaning and order of every previous
motor-status field and appends one terminal field:

```text
battery_resistance_mohm
```

The motor board sends `-1` before a valid result and repeats the measured value
in every later status for the rest of its boot. No one-shot packet is used,
because that packet could be lost during an `m RX!` outage.

Compatibility rules:

- an older Display ignores the appended field;
- a newer Display accepts an older status without the field and treats the
  result as unavailable;
- a newer Display accepts only `1..2500` and latches the first valid value per
  Display boot;
- repeated copies of the same motor result do not create additional history
  rows or alerts.

For temporary field diagnosis, the status frame appends six more values after
the result: numeric estimator state, a legacy reserved zero, failed-load count,
accepted load-sample count, accepted reference-sample count, and whole seconds
elapsed in an active phase. The states are `0` get reference, `1` ramp, `2` get
load, `3` collect, `4` complete, and `5` failed. During state `0`, the reference sample
count is the rolling set of last accepted reference samples. During states `2`
and `3`, the load sample count is the rolling set of accepted load samples. During
temporary field diagnosis, the Display exposes these values on `MAIN` so they
remain visible while riding.

Motor and Display normally share the scooter power cycle. If only the Display
resets after the motor has already measured, the repeated result is deliberately
treated as `THIS BOOT` by the new Display session and receives the new receipt
time. Distinguishing that exceptional case would require a motor boot identifier
or measurement age, which this compact protocol intentionally omits.

## RAM, files, and shutdown

At Display boot, load the small summary into RAM and scan the bounded history
file to reconcile an interrupted shutdown. The loader also checks a recoverable
`.tmp` summary. During operation only RAM is updated. On explicit Display
shutdown, before requesting relay-off:

1. append the current-boot result once to the PC-readable history CSV;
2. write a complete `summary.csv.tmp`;
3. replace the old summary, leaving the complete `.tmp` loadable throughout
   the remove/rename window;
4. then continue shutdown.

The order is intentional: a failed history append never publishes a newer
summary. If history succeeds but summary publication is interrupted, boot
reconstructs the last/min/max RAM state by merging the final complete history
rows with the newest valid summary generation. A retry in the same boot tracks
that the history row is already committed and does not append it twice.

The history file is capped at 100 KiB. When the next row would exceed the cap,
the existing history is removed and the same path is recreated with a header
and the new row. It does not retain a second rotated history generation. The
two configured persistent paths are:

- `battery_resistance_summary.csv`;
- `battery_resistance_history.csv`.

Example CSV snapshots are kept alongside this document:

- [battery_resistance_summary.csv](battery_resistance_summary.csv)
- [battery_resistance_history.csv](battery_resistance_history.csv)

These are documentation samples, not the runtime files. The firmware creates
the configured paths on the Display filesystem.

Automatic power-board timeout and abrupt power loss do not flush Display RAM;
losing the unpersisted result in those cases is an accepted design decision.

History format:

```text
timestamp,resistance_mohm
2026-08-13T14:32:10,83
na,79
```

Summary format:

```text
kind,resistance_mohm,timestamp
last,83,2026-08-13T14:32:10
min,71,2026-08-05T09:10:00
max,109,na
```

## Display requirements

The dedicated screen shows:

- the prominent last/current result;
- `THIS BOOT` when received during the current Display boot;
- `LAST SAVED` when loaded from the summary;
- centred historical Min and Max rows in the smaller existing font;
- `na` for unavailable values or timestamps.

On first receipt of a valid motor result, enqueue the normal-priority alert:

```text
R <value> moh
```

The default alert duration is five seconds and it is shown only by the normal
dashboard. The temporary resistance-debug dashboard already shows the result
in its state-specific lines, so it consumes the event without displaying or
delaying an alert. Repeated motor status frames must not enqueue the alert
again. The latch is per Display boot: if only the Display restarts while the
motor remains powered and keeps repeating its result, the new Display session
accepts it once and shows one new alert when the normal dashboard is active.

The screen is part of the existing manual stopped/brakes-on flow: a click moves
from `CHARGING` to `BATTERY_RESISTANCE`, and the next click returns to `BOOT`.
Automatic charging and Wi-Fi/NTP synchronization keep their existing charging
screen locks.

## Feature module boundary

For embedded robustness and host testability, new failure handling should stay
inside feature-specific modules. The target boundary is:

- `common/battery_resistance.py`: input freshness/skew classification,
  variable-interval tracking, attempt state, aggregation, and trimmed mean;
- `common/config_battery_resistance.py`: all feature thresholds and validation;
- a feature-local Display persistence module: summary/CSV parsing, bounded
  history writing, and shutdown save state;
- existing motor and Display entry points: thin adapters only.

Both the CAN input tracker and Display persistence have reached this boundary.
Host tests cover phased single/dual-VESC inputs, interrupted summary
replacement, history-write failure, recovery from a history-only commit, and
same-boot retry without a duplicate CSV row.

## Interpretation

Compare results at similar battery temperature, state of charge, and riding
conditions. A sustained increase can indicate battery ageing or resistance in
the BMS, fuse, connectors, or cabling, but it is not by itself a cell diagnosis.
