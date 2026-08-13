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

The calculation uses only VESC CAN data:

- `STATUS_4` supplies battery current;
- `STATUS_5` supplies battery voltage;
- independent timestamps determine freshness and voltage/current skew;
- every configured VESC must have a fresh valid voltage/current pair;
- in dual-motor mode, equivalent rear/front current timestamps and rear/front
  voltage timestamps must also be close enough to represent the same load.

The motor retains separate raw last-decoded battery voltage/current values for
the estimator. Operational telemetry can therefore continue expiring at its
shorter 500 ms safety timeout without turning an unrefreshed dual-motor branch
into an artificial 0 A input during the estimator's 1500 ms observation window.

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
an active branch, stale pair, or excessive voltage/current timestamp skew makes
the aggregate sample invalid.

## Measurement conditions

All timing uses monotonic `ticks_ms()` arithmetic on the motor board.

### 1. Boot delay

Do not start an attempt during the first three minutes after motor-board boot:

```text
boot_delay_ms = 180000
```

After the delay, failed attempts may be retried. Only the first successful
result completes the feature for that motor-board boot.

### 2. Reference sample

While total discharge current is above 2 A and below 15 A, retain the newest
fresh aggregate pair:

```text
Vref, Iref, tref
```

When current first reaches 15 A or more, freeze that reference. It is accepted
only when:

- it is no more than 1000 ms old;
- `Iload - Iref >= 10 A`;
- every configured VESC pair remains valid.

### 3. Five-second load qualification

Starting at the first aggregate sample with `Itotal >= 15 A`, require five
seconds of valid observed load. During this period:

- every observed aggregate current is at least 15 A;
- current remains within the configured ±2 A stability band relative to the
  load-start current;
- the gap between valid aggregate observations is no more than 1500 ms;
- no configured VESC reports negative battery current;
- no regen or invalid/stale voltage/current pair is observed.

A failure resets only the current attempt. The estimator can capture a new
reference and try again in the same boot.

Continuity means continuity of valid observations. One valid observation per
second is sufficient. The firmware does not attempt to reconstruct current
changes inside CAN frames that were never received.

### Asynchronous input tracking

`BatteryResistanceEstimator` owns the variable-interval input tracker inside
`common/battery_resistance.py`. It observes each VESC's independent counters,
raw values, and `STATUS_4`/`STATUS_5` timestamps and classifies a snapshot as:

- pending: one half is missing, stale, or temporarily over-skew; preserve the
  attempt until `motor_sample_gap_ms` expires;
- invalid: malformed values, negative current, impossible timestamps, regen,
  or a coherent invalid aggregate; cancel only the current attempt;
- valid: all configured VESC pairs and dual-VESC timestamps are coherent;
  advance the monitor.

Current timestamps are also evaluated independently of voltage. Therefore a
new observed total below 15 A or outside the ±2 A stability band cancels an
active plateau immediately even while its matching voltage half is pending.
The motor entry point makes one feature call per 50 ms refresh cycle. This
input-tracking correction adds no CAN or ESP-NOW protocol fields.

### 4. First three delayed samples

After the five-second qualification completes, accept the first three valid
aggregate samples available, subject to:

- at least 500 ms between accepted resistance samples;
- the same current, freshness, skew, stability, and observation-gap rules;
- all three samples collected within five seconds after qualification.

Examples:

- with fast telemetry: 5.0 s, 5.5 s, and 6.0 s after load start;
- with one useful observation per second: 5 s, 6 s, and 7 s;
- if three samples are not available by 10 s after load start: reset the
  attempt and wait for a new reference.

For every accepted sample:

```text
R_mOhm = 1000 * (Vref - Vsample) / (Isample - Iref)
```

The current step must remain at least 10 A and the voltage drop must be
positive. Each result must be in the inclusive configured range:

```text
1 <= R_mOhm <= 2500
```

The final result is the median of the three samples. Median is used instead of
mean so one disturbed voltage sample has less influence.

## Configuration contract

`common/config_battery_resistance.py` contains the shared settings. Ownership
and validation are split:

- the motor board validates boot delay, thresholds, freshness/skew, plateau,
  sample spacing/collection timeout, sample count, and resistance range;
- the Display validates only accepted result range, alert duration, filenames,
  and history size.

An invalid motor-side setting disables only the estimator and leaves general
CAN expiry/safety behaviour unchanged. An invalid Display persistence/UI setting
must not disable motor-side measurement or abort Display boot.

Implemented sampling settings:

```text
boot_delay_ms = 180000
load_qualify_ms = 5000
sample_count = 3
sample_min_interval_ms = 500
sample_collection_timeout_ms = 5000
reference_max_age_ms = 1000
motor_sample_gap_ms = 1500
vesc_signal_max_age_ms = 1500
vesc_voltage_current_max_skew_ms = 250
dual_vesc_max_skew_ms = 250
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
