import busio

class display(object):
    """Display"""
    def __init__(self, uart_tx_pin, uart_rx_pin):
        """Display
        :param ~microcontroller.Pin uart_tx_pin: UART TX pin that connects to VESC
        :param ~microcontroller.Pin uart_tx_pin: UART RX pin that connects to VESC
        """

        # configure UART for communications with display
        self.uart = busio.UART(uart_tx_pin, uart_rx_pin, baudrate = 19200)
