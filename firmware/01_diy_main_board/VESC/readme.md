# VESC standard telemetry and SOC

Set CAN baud rate to 125K, as configured by the maintained scooter profiles.

Install `battery_precision_telemetry.lisp` only on the rear VESC (CAN ID `0`).
It sends the rear VESC battery SOC as project-private command `99`, once per
second. It does not reset the VESC motor-command timeout.

The Motor Board receives all operational telemetry from normal VESC CAN
packets. In VESC Tool, App Settings → General → CAN Messages Rate 1:

- set Status Rate 1 to 10 Hz;
- enable Status 1, 4 and 5.
