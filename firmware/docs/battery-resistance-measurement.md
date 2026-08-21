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

`STATUS_4` and `STATUS_5` remain the normal operational telemetry and retain
their 500 ms safety timeout. They are deliberately not estimator inputs, so
their ×0.1-unit CAN quantisation and independent delivery cannot disturb the
resistance calculation.

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

The equivalent voltage is current-weighted, so a controller carrying little or
no current does not receive equal weight:

```text
Vequiv = (Vrear * Irear + Vfront * Ifront) / Itotal
```

For a single-motor configuration, `Itotal` and `Vequiv` are simply that VESC's
values. A negative current from either configured VESC, non-positive voltage on
any configured branch, stale pair, or excessive rear/front timestamp skew makes
the aggregate sample invalid.

## Measurement conditions

All timing uses monotonic `ticks_ms()` arithmetic on the motor board.

### 1. Boot qualification

Before attempting a measurement, accumulate 60 distinct elapsed seconds since
motor-board boot in which at least one valid aggregate observation has
`Vequiv * Itotal >= 200 W`:

```text
boot_qualifying_power_min_w = 200
boot_qualifying_seconds = 60
```

Several frames in the same elapsed second count as one second. The qualifying
seconds need not be consecutive: a later second with one valid `>= 200 W`
observation adds one to the total. Once the total reaches 60, failed attempts
may be retried. Only the first successful result completes the feature for that
motor-board boot.

### 2. Reference qualification and samples

After boot qualification, require 15 continuous seconds below 200 W:

```text
reference_power_max_w = 200
reference_qualify_ms = 15000
```

Each elapsed second needs at least one valid observation. An observation at
200 W or more, regen, malformed data, or a second without a valid observation
restarts this phase. During qualification, keep the latest three fresh
aggregate pairs, separated by at least 500 ms. Zero total current is valid in
this phase; in dual-motor mode the equivalent voltage is then the mean of the
two VESC voltages. At the end of the 15 continuous seconds, use the
independent medians as:

```text
Vref = median(Vref_samples)
Iref = median(Iref_samples)
```

Once qualification and its rolling samples are complete, the estimator waits
for the high-load phase. The qualified reference intentionally has no maximum
age: intermediate observations below the load threshold preserve it until a
load attempt starts or another reset condition occurs.

### 3. Ten-second load qualification

Starting at the first aggregate sample with `Vequiv * Itotal >= 750 W`, require
ten seconds of valid observed load. During this period:

- every observed aggregate power is at least 750 W;
- every elapsed second has at least one valid aggregate observation;
- no configured VESC reports negative battery current;
- no regen or invalid/stale precision pair is observed.

A failure resets only the current attempt. The estimator can collect a new
reference and try again in the same boot.

During temporary field diagnosis, the Display `MAIN` screen is replaced by a
five-line resistance status view. This makes the live estimator phase and its
rolling sample progress visible while riding; it does not change motor control
or command a measurement load. The normal resistance-history screen remains
available from the manual charging-screen flow. Normal riding indicators and
warnings are intentionally omitted from this temporary diagnostic view.

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
- invalid: malformed values, negative current, impossible timestamps, regen,
  or a coherent invalid aggregate; cancel only the current attempt;
- valid: all configured VESC pairs and rear/front timestamps are coherent;
  advance the monitor.

The motor entry point makes one feature call per 50 ms refresh cycle. The
source frame is VESC-local and no synchronised LISP clock is assumed.

### 4. Last three load samples

During the ten-second qualification window, accept valid aggregate samples
subject to:

- at least 500 ms between accepted resistance samples;
- the same power and freshness rules;
- keep only the last three accepted samples in the qualification window.

Examples:

- with fast telemetry, the rolling window contains the samples closest to the
  end of the 10-second qualification;
- with one useful observation per second, the final window is normally at 8 s,
  9 s, and 10 s after load start;
- if fewer than three valid samples are accepted by qualification end, reset
  the attempt and collect a new reference.

For every accepted sample:

```text
R_mOhm = 1000 * (Vref - Vsample) / (Isample - Iref)
```

The current must be above the reference current and the voltage drop must be
positive. Each result must be in the inclusive configured range:

```text
1 <= R_mOhm <= 2500
```

The final result is the median of the last three samples. Median is used
instead of mean so one disturbed voltage sample has less influence.

## Configuration contract

`common/config_battery_resistance.py` contains the shared settings. Ownership
and validation are split:

- the motor board validates boot qualification, power thresholds,
  freshness/skew, qualification duration, sample spacing/collection timeout,
  sample count, and resistance range;
- the Display validates only accepted result range, alert duration, filenames,
  and history size.

An invalid motor-side setting disables only the estimator and leaves general
CAN expiry/safety behaviour unchanged. An invalid Display persistence/UI setting
must not disable motor-side measurement or abort Display boot.

Implemented sampling settings:

```text
boot_qualifying_power_min_w = 200
boot_qualifying_seconds = 60
reference_power_max_w = 200
reference_qualify_ms = 15000
load_power_min_w = 750
load_qualify_ms = 10000
sample_count = 3
sample_min_interval_ms = 500
sample_collection_timeout_ms = 5000
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

For temporary field diagnosis, the status frame appends five more values after
the result: numeric estimator state, boot-qualification seconds, reset/error
counter, accepted load-sample count, and accepted reference-sample count. The
states are `0` reference qualification, `1` waiting for load, `2` load
qualification, and `3` complete. During state `0`, the reference sample count
is the rolling set of last accepted reference samples. During state `2`, the
load sample count is the rolling set of last accepted load samples. During
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
R <value> mOhm
```

The default alert duration is five seconds. Repeated motor status frames must
not enqueue the alert again. The latch is per Display boot: if only the Display
restarts while the motor remains powered and keeps repeating its result, the
new Display session accepts it once and shows one new alert.

The screen is part of the existing manual stopped/brakes-on flow: a click moves
from `CHARGING` to `BATTERY_RESISTANCE`, and the next click returns to `BOOT`.
Automatic charging and Wi-Fi/NTP synchronization keep their existing charging
screen locks.

## Feature module boundary

For embedded robustness and host testability, new failure handling should stay
inside feature-specific modules. The target boundary is:

- `common/battery_resistance.py`: input freshness/skew classification,
  variable-interval tracking, attempt state, aggregation, and median;
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
