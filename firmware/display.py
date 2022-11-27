import busio
from enum import Enum

class display(object):
    """Display"""
    def __init__(self, uart_tx_pin, uart_rx_pin):
        """Display
        :param ~microcontroller.Pin uart_tx_pin: UART TX pin that connects to VESC
        :param ~microcontroller.Pin uart_tx_pin: UART RX pin that connects to VESC
        """

        # configure UART for communications with display
        self.uart = busio.UART(uart_tx_pin, uart_rx_pin, baudrate = 19200)

        self.uart_process

    #every 50ms, read and process UART data
    def process_data(self):
        return 0

class packet(object):
    def __init__(self):
        self.state = 0

    