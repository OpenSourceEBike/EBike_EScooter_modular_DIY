On App Settings -> General, set CAN Baud Rate to 125K. This is the frequency the main board expects.

Install [battery_precision_telemetry.lisp](battery_precision_telemetry.lisp)
in the VESCTool LISP tab on **both** VESCs. Set `vesc-id` to `0` on the rear
VESC and `1` on the front VESC before running it.

The script sends three project-private extended CAN frames:

- command `101`: local VESC input voltage as unsigned 32-bit mV followed by
  input current as signed 32-bit mA, at 10 Hz. Its eight-byte payload supports
  currents beyond the signed-16-bit range while retaining 1 mA resolution.
- command `102`: electrical RPM as signed 32-bit, motor current as signed
  ×10 A 16-bit, sequence, and flags, at 10 Hz immediately after `101`.
- command `103`: VESC temperature ×10 C, motor temperature ×10 C, battery
  SOC ×1000, sequence, and flags, at 2 Hz.

The motor ESP32 timestamps every family separately. It consumes only these
three project-private frames. VESC ID 1 waits 50 ms before starting, which
separates the two 10 Hz `101`/`102` bursts on the shared CAN bus.

The exact same program and payload layout run on both VESCs; only `vesc-id`
changes. The motor ESP32 ignores front ERPM and SOC instead of storing them,
while still using both input voltage/current pairs, front motor current, and
front temperatures.

On App Settings -> General, on CAN Messages Rate 1:
- Disable Status 1, 4 and 5.
