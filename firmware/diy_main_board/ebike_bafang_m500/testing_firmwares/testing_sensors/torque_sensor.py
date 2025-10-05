import canio
import time
import struct

class TorqueSensor(object):

    def __init__(self, can_tx_pin, can_rx_pin, cadence_timeout = 1.0):
        """Torque sensor
        :param ~microcontroller.Pin can_tx_pin: the pin to use for the can_tx_pin.
        :param ~microcontroller.Pin can_rx_pin: the pin to use for the can_rx_pin.
        :param float cadence_timeout: timeout in seconds, to reset cadence value if no new value higher than 0 is read
        """

        self._can_bus = canio.CAN(can_tx_pin, can_rx_pin, baudrate = 250000)
        self._cadence_timeout = cadence_timeout
        self._cadence_previous_time = 0
        self._cadence_previous = 0
        self._cadence = 0
        self._torque_weight = 0

    @property
    def value_raw(self):
        """Torque sensor raw values
        return: torque, cadence and progressive_byte
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value
                progressive_byte = msg.data[3] # last byte should be a value that increases on each package

                return torque[0], cadence[0], progressive_byte
            else:
                return None, None

    @property
    def value(self):
        """Torque sensor value
        return: torque, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque[0], cadence[0]
            else:
                return None, None

    @property
    def weight_value(self):
        """Torque sensor weight value
        return: torque weight, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            if listener.in_waiting():
                msg = listener.receive()

                # unpack values from the byte array
                torque = struct.unpack_from('<H', msg.data, 0) # 2 bytes: torque value
                torque = (torque[0] - 750) / 61 # convert to kgs
                cadence = struct.unpack_from('<B', msg.data, 2) # 1 byte: cadence value

                return torque, cadence[0]
            else:
                return None, None
              
    @property
    def weight_value_cadence_filtered(self):
        """Torque sensor weight value with cadence filtered
        return: torque weight, cadence
        """
        with self._can_bus.listen(timeout=1.0) as listener:
            
            msg = bytearray()
            cadence = None
            torque = None
            now = time.monotonic()
            counter = 0

            while True:
                if listener.in_waiting():
                    msg = listener.receive()

                    cadence = msg.data[2]
                    if cadence > 0:
                        # we got a new cadence value
                        self._cadence_previous_time = now
                        self._cadence_previous = cadence

                        torque = (msg.data[1] * 256) + msg.data[0]
                        torque = (torque - 750) / 61 # convert to kgs

                        # ignore previous messages, just clean them
                        while listener.in_waiting():
                            listener.receive()

                        return torque, cadence
                    
                    else:
                        # cadence is 0
                      
                        counter += 1
                        # check if previous 5 messages are always 0, if so, stop here
                        if counter > 5:
                            # check for cadence timeout
                            timeout = True if now > (self._cadence_previous_time + self._cadence_timeout) else False
                            if timeout:
                                self._cadence_previous = 0
                                self._cadence_previous_time = now
                            else:
                                # keep cadence with previous value
                                cadence = self._cadence_previous

                            torque = (msg.data[1] * 256) + msg.data[0]
                            torque = (torque - 750) / 61 # convert to kgs
                            
                            # ignore previous messages, just clean them
                            while listener.in_waiting():
                                listener.receive()

                            return torque, cadence
                          
                else:
                # check for cadence timeout
                    timeout = True if now > (self._cadence_previous_time + self._cadence_timeout) else False
                    if cadence == 0:
                        # we got cadence = 0
                        if timeout:
                            self._cadence_previous = 0
                            self._cadence_previous_time = now
                        else:
                            # keep cadence with previous value
                            cadence = self._cadence_previous

                        torque = (msg.data[1] * 256) + msg.data[0]
                        torque = (torque - 750) / 61 # convert to kgs

                    else:
                        # we got no new values from torque sensor
                        if timeout:
                            self._cadence_previous = 0
                            self._cadence_previous_time = now
                        else:
                            cadence = self._cadence_previous

                    return torque, cadence