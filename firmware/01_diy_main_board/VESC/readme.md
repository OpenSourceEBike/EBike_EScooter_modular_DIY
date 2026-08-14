On App Settings -> General, set CAN Baud Rate to 125K. This is the frequency the main board expects.

Install [battery_precision_telemetry.lisp](battery_precision_telemetry.lisp)
in the VESCTool LISP tab on **both** VESCs. Set `vesc-id` to `0` on the rear
VESC and `1` on the front VESC before running it.

The script sends two project-private extended CAN frames:

- command `100`: battery SOC in the existing ×1000 format, at 1 Hz;
- command `101`: local VESC input voltage as unsigned 32-bit mV followed by
  input current as signed 32-bit mA, at 10 Hz. Its eight-byte payload supports
  currents beyond the signed-16-bit range while retaining 1 mA resolution.

The motor ESP32 timestamps frame receipt and only combines rear/front command
`101` samples that arrive in the same short window. This preserves the VESC
filtered measurement resolution and avoids assuming synchronised Lisp clocks.
The display retains the last SOC for up to 30 seconds; the shorter 500 ms
timeout still applies only to fast control/status families.

The main boards needs to read periodically data from the VESC like battery voltage and motor current, for that, the following CAN messages should be enabled:
On App Settings -> General, on CAN Messages Rate 1:
- Set CAN Status Rate 1 to 10Hz
- Enable Status 1, 4 and 5
