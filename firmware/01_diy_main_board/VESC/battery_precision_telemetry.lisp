; Read VESC battery SOC and send it to CAN once per second.
; Standard VESC CAN Status 1, 4 and 5 provide all other motor telemetry.
; Install this on the rear VESC (CAN ID 0).

(def id 0)
(def command 99)
(def canid (bits-enc-int id 8 command 8))

(loopwhile t {
        (def battsoc (to-i(*(get-batt) 1000)))
        (def canmsg (list
                (shr (bitwise-and battsoc 0xff00) 8)
                (bitwise-and battsoc 0xFF)))
        (can-send-eid canid canmsg)
        (timeout-reset)
        (sleep 1.0)
})
