; High-resolution battery telemetry for the scooter motor board.
;
; Install the same program on both VESCs, changing vesc-id to the VESC CAN ID:
;   rear:  0
;   front: 1
;
; Project-private extended CAN telemetry. All payloads are big endian.
;
; Command 101 (every 100 ms):
;   bytes 0..3: input voltage in mV, unsigned 32-bit
;   bytes 4..7: input current in mA, signed 32-bit
;
; Command 102 (every 100 ms, immediately after 101):
;   bytes 0..3: electrical RPM, signed 32-bit
;   bytes 4..5: motor current in 0.1 A, signed 16-bit
;   byte 6: sequence counter; byte 7: reserved flags
;
; Command 103 (every 500 ms):
;   bytes 0..1: VESC temperature in 0.1 C, unsigned 16-bit
;   bytes 2..3: motor temperature in 0.1 C, unsigned 16-bit
;   bytes 4..5: battery SOC x1000, unsigned 16-bit
;   byte 6: sequence counter; byte 7: reserved flags
;
; These are the only telemetry frames consumed by the motor ESP32. VESC ID 1
; starts 50 ms later than ID 0, so the two VESCs do not send their 101/102
; pairs together.
; The receiver uses both VESC input voltages/currents for battery aggregation.
; ERPM and SOC from VESC ID 1 are transmitted in the common layout but ignored
; by the motor ESP32.

(def vesc-id 0)
(def precision-command 101)
(def motion-command 102)
(def thermal-command 103)

(def precision-canid
        (bits-enc-int vesc-id 8 precision-command 8))

(def motion-canid
        (bits-enc-int vesc-id 8 motion-command 8))

(def thermal-canid
        (bits-enc-int vesc-id 8 thermal-command 8))

(def thermal-period-samples 5)
(def thermal-sample-counter 4)
(def motion-sequence 0)
(def thermal-sequence 0)

; Keep the two VESC telemetry bursts apart on the shared CAN bus.
(sleep (* vesc-id 0.05))

(loopwhile t {
        ; get-vin and get-current-in are VESC filtered float measurements.
        (def battery-soc-x1000
                (to-i (* (get-batt) 1000)))

        (def battery-voltage-mv
                (to-i (* (get-vin) 1000)))

        (def battery-current-ma
                (to-i (* (get-current-in) 1000)))

        (def motor-erpm (to-i (get-rpm)))
        (def motor-current-x10 (to-i (* (get-current) 10)))

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

        (def motion-msg
                (list
                        (bitwise-and (shr motor-erpm 24) 0xFF)
                        (bitwise-and (shr motor-erpm 16) 0xFF)
                        (bitwise-and (shr motor-erpm 8) 0xFF)
                        (bitwise-and motor-erpm 0xFF)
                        (bitwise-and (shr motor-current-x10 8) 0xFF)
                        (bitwise-and motor-current-x10 0xFF)
                        (bitwise-and motion-sequence 0xFF)
                        0))

        ; Keep the fast pair adjacent in this cycle.
        (can-send-eid precision-canid precision-msg)
        (can-send-eid motion-canid motion-msg)
        (def motion-sequence (+ motion-sequence 1))
        (if (= motion-sequence 256) {
                (def motion-sequence 0)
        })

        (def thermal-sample-counter (+ thermal-sample-counter 1))

        (if (= thermal-sample-counter thermal-period-samples) {
                (def vesc-temperature-x10 (to-i (* (get-temp-fet) 10)))
                (def motor-temperature-x10 (to-i (* (get-temp-mot) 10)))
                (def thermal-msg
                        (list
                                (bitwise-and (shr vesc-temperature-x10 8) 0xFF)
                                (bitwise-and vesc-temperature-x10 0xFF)
                                (bitwise-and (shr motor-temperature-x10 8) 0xFF)
                                (bitwise-and motor-temperature-x10 0xFF)
                                (bitwise-and (shr battery-soc-x1000 8) 0xFF)
                                (bitwise-and battery-soc-x1000 0xFF)
                                (bitwise-and thermal-sequence 0xFF)
                                0))
                (can-send-eid thermal-canid thermal-msg)
                (def thermal-sequence (+ thermal-sequence 1))
                (if (= thermal-sequence 256) {
                        (def thermal-sequence 0)
                })
                (def thermal-sample-counter 0)
        })

        (sleep 0.1)
})
