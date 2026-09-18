# Passive BMS battery-resistance measurement

The Display estimates sustained-load DC resistance exclusively from the JBD
Bluetooth BASIC (`0x03`) pack-voltage and pack-current values. No VESC LispBM
estimator, CAN command `104`, or Motor Board resistance payload exists.

This is an effective pack measurement at the BMS measurement point and its BLE
sampling timescale. It is not an instantaneous cell electrochemical impedance,
nor a traction-control input.

## Input and sampling boundary

The JBD client requests BASIC and cell frames alternately every second. BASIC
voltage/current samples consequently arrive at roughly two-second intervals.
The estimator consumes a sample only when `last_basic_data_ms` changes; a UI
cycle that sees the same cached BASIC frame twice cannot create a measurement.

JBD current is signed: discharge is negative and charging/regen is positive.
The first implementation intentionally measures discharge steps only.

## Algorithm

1. Keep a 16-sample circular buffer of `(timestamp_ms, voltage_x100,
   current_x100)`.
2. Reject and reset an in-progress event if the same BASIC frame reports an
   active BMS protection. The JBD client does not expose MOSFET state, and the
   estimator does not use it.
3. Establish a reference from three new BASIC samples where every pack power
   is within -250 W to +250 W.
4. Detect a discharge event only if pack power is at least -750 W.
5. Discard the next new BASIC frame as a settling frame, then collect three
   load samples that remain at or below -750 W. The complete event must finish
   within the configurable 15 seconds from the detected step; otherwise it
   resets to `REFERENCE`.
6. Calculate integer-rounded resistance:

```text
R_mOhm = round(1000 * (V_before - V_after) / abs(I_after - I_before))
```

Results with non-positive voltage sag, voltage sag below 0.10 V, or values
outside 1..500 mOhm are rejected.

For example, 53.81 V / -1.30 A followed by 51.70 V / -61.30 A produces
`round(1000 * 2.11 / 60) = 35 mOhm`.

The main dashboard shows compact sample progress: `R0/3` through `R3/3` for
reference, `S0/1` while the settling frame is pending, `L0/3` through `L3/3`
for load, and `OK` after a result. The full states are `REFERENCE`,
`SETTLE`, `LOAD`, and `COMPLETE`; elapsed seconds remain available to the
history screen. Any BMS disconnect, stale BASIC frame, active BMS
protection, expired load event, or Wi-Fi/NTP radio handover resets the
in-progress estimator. Normal charging detection, motor telemetry, and traction
remain independent.

## Persistence and validation

Results are Display-local and use separate files:

```text
bms_battery_resistance_history.csv
bms_battery_resistance_summary.csv
```

Rows retain the reference/load voltage and current used by the accepted result.
Existing VESC-derived history files are neither read nor overwritten.

Host tests cover a known 35 mOhm step, duplicate BASIC timestamps, regeneration
rejection, active-protection rejection, power-window/load-threshold behavior,
variable sustained-load behavior, and late-load event expiry. Hardware
validation still needs real BLE timing, BMS filtering behavior, temperature/SOC
repeatability, and comparison with a calibrated external load.
