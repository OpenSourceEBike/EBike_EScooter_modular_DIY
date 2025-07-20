The following code must be placed on VESCTool, on the LISP tab.

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