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

The battery-resistance screen shows the last result, the current estimator
phase (`REFERENCE`, `SETTLE`, `LOAD`, or `COMPLETE`), sample progress, and
minimum and maximum results. Once all reference samples have been collected,
the screen shows `WAIT LOAD` with `BASELINE: 3/3` until a qualifying discharge
step arrives. It shows `WAIT BMS` until fresh BASIC data is
available. Elapsed seconds remain available to the history screen. Any BMS
disconnect, stale BASIC frame, active BMS
protection, expired load event, or Wi-Fi/NTP radio handover resets the
in-progress estimator. Normal charging detection, motor telemetry, and traction
remain independent.

If the BMS is absent during startup, the client makes two immediate reconnect
attempts and then waits 30 seconds before automatically starting a new bounded
scan sequence. Three consecutive unexpected client `tick()` failures also
enter that recovery path. Every BLE connection boundary discards cached
measurements and unread stream bytes, so neither a previous value nor a complete
or partial previous frame can be exposed by the new connection. A JBD response
is accepted only when its status is success, its declared length matches, and
its checksum over status, length and data is exact.

## Persistence and validation

Results are Display-local and use separate files:

```text
bms_battery_resistance_history.csv
bms_battery_resistance_summary.csv
```

Rows retain only timestamp, measured resistance, and the first JBD NTC value in
degrees Celsius times 100 (`bms_temperature_c_x100`). If no NTC value is
available, the temperature is stored as `na`. Existing six-column BMS history
files are migrated to this format without dropping valid timestamp/resistance
records; their temperature is `na`. A complete migration temporary file is
recovered and published on the next persistence attempt after a reset or power
loss during the rename.

Each completed measurement is placed in a bounded pending queue and persisted
immediately; it is not deferred until the rider requests shutdown. A failed
filesystem transaction remains queued and is retried every five seconds, while
explicit shutdown remains the final flush path. Consequently, several results
in one display boot produce several history rows, and the independent Power
Board inactivity cutoff cannot normally remove power before a result is saved.
The queue holds up to 16 results during a persistent storage failure; once full,
new results are rejected rather than silently coalesced or allowing unbounded
RAM growth.

Host tests cover a known 35 mOhm step, duplicate BASIC timestamps, regeneration
rejection, active-protection rejection, power-window/load-threshold behavior,
variable sustained-load behavior, late-load event expiry, connection-buffer
discard, strict checksum/status validation, and multi-result persistence.
Hardware
validation still needs real BLE timing, BMS filtering behavior, temperature/SOC
repeatability, and comparison with a calibrated external load.
