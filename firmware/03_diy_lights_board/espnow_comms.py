# espnow_comms.py - MicroPython ESP-NOW helper for lights board (ESP32-C3)

import network
import espnow

from constants import FRONT_VERSION, REAR_VERSION

# These IDs must match the ones used by the transmitter.
try:
    from common.boards_ids import BoardsIds
except ImportError:
    raise Exception(
        "error importing file: firmware_common/boards_ids.py\n"
        "Place the folder 'firmware_common' on the root path"
    )


class ESPNowComms:
    def __init__(self, mac_address, lights_board, channel: int = 1):
        """
        MicroPython ESP-NOW helper for the DIY lights board.

        Args:
            mac_address: Iterable with 6 bytes for the local Wi-Fi MAC address.
            lights_board: FRONT_VERSION or REAR_VERSION (see constants.py).
            channel: Wi-Fi channel to use for ESP-NOW (default: 1).
        """
        # Wi-Fi station interface
        sta = network.WLAN(network.STA_IF)
        self._sta = sta

        if not sta.active():
            sta.active(True)

        # Ensure disconnected from any AP
        try:
            sta.disconnect()
        except Exception:
            # Already disconnected or not associated
            pass

        # Configure Wi-Fi channel
        try:
            sta.config(channel=channel)
        except Exception as e:
            print("Warning: couldn't set Wi-Fi channel:", e)

        # Set local MAC address
        try:
            my_mac = bytes(mac_address)
            if len(my_mac) != 6:
                raise ValueError("mac_address must be 6 bytes long")
            sta.config(mac=my_mac)
        except Exception as e:
            print("Warning: couldn't set local MAC:", e)

        # Initialize ESP-NOW
        self._esp = espnow.ESPNow()
        self._esp.active(True)

        # Identify this board using predefined board IDs
        if lights_board == FRONT_VERSION:
            self._board_id = int(BoardsIds.FRONT_LIGHTS)
        elif lights_board == REAR_VERSION:
            self._board_id = int(BoardsIds.REAR_LIGHTS)
        else:
            raise ValueError("Invalid lights_board in ESPNowComms")

    def get_data(self):
        """
        Read ESP-NOW packets (non-blocking) and return the last valid message
        addressed to this board_id.

        Expected message format (ASCII):
            "<board_id> <value>"
        Example:
            "3 5"

        Returns:
            The integer <value> for this board, or None if no valid message.
        """
        received_value = None
        last_msg = None

        try:
            # Read all queued packets; keep only the last one
            while True:
                host, msg = self._esp.recv(0)  # timeout=0 -> non-blocking
                if msg is None:
                    break
                last_msg = msg
        except OSError:
            # No messages or minor recv error
            pass
        except Exception as ex:
            print("ESP-NOW recv error:", ex)
            return None

        if last_msg is None:
            return None

        try:
            # Parse ASCII message "<id> <value>"
            parts = [int(n) for n in last_msg.split()]
        except Exception as ex:
            print("ESP-NOW parse error:", ex)
            return None

        # Must contain exactly 2 integers and be addressed to this board
        if (len(parts) == 2) and (parts[0] == self._board_id):
            received_value = parts[1]

        return received_value

    def send_data(self, *args, **kwargs):
        """
        Placeholder method (same as original CircuitPython version).
        Implement this if you need the lights board to transmit ESP-NOW data.
        """
        pass
