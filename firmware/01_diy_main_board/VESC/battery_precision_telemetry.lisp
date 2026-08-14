; High-resolution battery telemetry for the scooter motor board.
;
; Install the same program on both VESCs, changing vesc-id to the VESC CAN ID:
;   rear:  0
;   front: 1
;
; Custom command 101 payload (big endian, every 100 ms):
;   bytes 0..3: input voltage in mV, unsigned 32-bit
;   bytes 4..7: input current in mA, signed 32-bit
;
; This supports voltages above 150 V and currents above +/-100 A
; while keeping 1 mV and 1 mA resolution.
; The ESP32 receives each VESC's local sample and combines only recent pairs.

(def vesc-id 0)
(def soc-command 100)
(def precision-command 101)

(def soc-canid
        (bits-enc-int vesc-id 8 soc-command 8))

(def precision-canid
        (bits-enc-int vesc-id 8 precision-command 8))

(def soc-period-samples 10)

; Start at 9 so a useful SOC is sent immediately after Lisp starts.
(def soc-sample-counter 9)

(loopwhile t {
        ; get-vin and get-current-in are VESC filtered float measurements.
        (def battery-soc-x1000
                (to-i (* (get-batt) 1000)))

        (def battery-voltage-mv
                (to-i (* (get-vin) 1000)))

        (def battery-current-ma
                (to-i (* (get-current-in) 1000)))

        ; SOC: unsigned 16-bit, x1000.
        (def soc-msg
                (list
                        (bitwise-and (shr battery-soc-x1000 8) 0xFF)
                        (bitwise-and battery-soc-x1000 0xFF)))

        ; Precision telemetry:
        ;   voltage: unsigned 32-bit, mV
        ;   current: signed 32-bit, mA
        (def precision-msg
                (list
                        ; Voltage
                        (bitwise-and (shr battery-voltage-mv 24) 0xFF)
                        (bitwise-and (shr battery-voltage-mv 16) 0xFF)
                        (bitwise-and (shr battery-voltage-mv 8) 0xFF)
                        (bitwise-and battery-voltage-mv 0xFF)

                        ; Current
                        (bitwise-and (shr battery-current-ma 24) 0xFF)
                        (bitwise-and (shr battery-current-ma 16) 0xFF)
                        (bitwise-and (shr battery-current-ma 8) 0xFF)
                        (bitwise-and battery-current-ma 0xFF)))

        ; Send voltage/current at 10 Hz.
        (can-send-eid precision-canid precision-msg)

        ; SOC changes slowly, so send it every tenth 10 Hz precision sample.
        (def soc-sample-counter
                (+ soc-sample-counter 1))

        (if (= soc-sample-counter soc-period-samples) {
                (can-send-eid soc-canid soc-msg)
                (def soc-sample-counter 0)
        })

        (sleep 0.1)
})