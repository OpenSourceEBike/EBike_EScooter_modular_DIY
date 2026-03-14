On App Settings -> General, set CAN Baud Rate to 125K. This is the frequency the main board expects.

The following code must be placed on VESCTool, on the LISP tab.
This code reads the VESC battery SOC and sends it to CAN, every 1 second, so the main board can read the battery SOC.

```lisp
; This code reads the VESC battery SOC and sends it to CAN, every 1 second
(def id 0)
(def command 99)
(def canid (bits-enc-int id 8 command 8))

(loopwhile t {
        (def battsoc (to-i(*(get-batt) 1000)))
        (def canmsg (list (shr (bitwise-and battsoc 0xff00) 8) (bitwise-and battsoc 0xFF)))
        (can-send-eid canid canmsg)
        (timeout-reset)
        (sleep 1.0)
})
```

The main boards needs to read periodically data from the VESC like battery voltage and motor current, for that, the following CAN messages should be enabled:
On App Settings -> General, on CAN Messages Rate 1:
- Set CAN Status Rate 1 to 10Hz
- Enable Status 1, 4 and 5
