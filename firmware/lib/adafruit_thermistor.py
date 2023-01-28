# SPDX-FileCopyrightText: 2017 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_thermistor`
===========================================================

A thermistor is a resistor that varies with temperature. This driver takes the
parameters of that resistor and its series resistor to determine the current
temperature. To hook one up, connect an analog input pin to the connection
between the resistor and the thermistor.  Be careful to note if the thermistor
is connected on the high side (from analog input up to high logic level/3.3 or
5 volts) or low side (from analog input down to ground).  The initializer takes
an optional high_side boolean that defaults to True and indicates if that the
thermistor is connected on the high side vs. low side.

* Author(s): Scott Shawcroft

Implementation Notes
--------------------

**Hardware:**

* Adafruit `10K Precision Epoxy Thermistor - 3950 NTC <https://www.adafruit.com/products/372>`_
  (Product ID: 372)

* Adafruit `Circuit Playground Express <https://www.adafruit.com/products/3333>`_
  (Product ID: 3333)

**Software and Dependencies:**

* Adafruit CircuitPython firmware: https://github.com/adafruit/circuitpython/releases

**Notes:**

#. Check the datasheet of your thermistor for the values.
"""

import math
import analogio

try:
    import typing  # pylint: disable=unused-import
    import microcontroller
except ImportError:
    pass

__version__ = "3.4.7"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_Thermistor.git"


class Thermistor:
    """
    :param ~microcontroller.Pin pin: Analog pin used for the thermistor
    :param int series_resistor: resistance in series between you analog input and the
     thermistor, normally a 10K resistor is placed between VCC and the analog pin
    :param int nominal_resistance: nominal resistance of the thermistor. normally 10k
    :param int b_coefficient: thermistor's B coefficient. Typically this is a value in
     the range of 3000-4000
    :param bool high_side: indicates if the thermistor is connected on the high side or
     low side of the resistor. Defaults to `True`


    **Quickstart: Importing and using the adafruit_thermistor library**

        Here is one way of importing the `Thermistor` class so you can use it
        with the name ``thermistor``.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            import adafruit_thermistor

        Once this is done you can define your `Thermistor` object and define your sensor object

        .. code-block:: python

            thermistor = adafruit_thermistor.Thermistor(board.A0, 10000, 10000, 25, 3950)

        Now you have access to the temperature with the :attr:`temperature` attribute.
        This temperature is in Celsius.


        .. code-block:: python

            temperature = thermistor.temperature

    """

    def __init__(
        self,
        pin: microcontroller.Pin,
        series_resistor: int,
        nominal_resistance: int,
        nominal_temperature: int,
        b_coefficient: int,
        *,
        high_side: bool = True
    ) -> None:
        # pylint: disable=too-many-arguments
        self.pin = analogio.AnalogIn(pin)
        self.series_resistor = series_resistor
        self.nominal_resistance = nominal_resistance
        self.nominal_temperature = nominal_temperature
        self.b_coefficient = b_coefficient
        self.high_side = high_side

    @property
    def resistance(self) -> float:
        """The resistance of the thermistor in Ohms"""
        if self.high_side:
            # Thermistor connected from analog input to high logic level.
            reading = self.pin.value / 64
            reading = (1023 * self.series_resistor) / reading
            reading -= self.series_resistor
        else:
            # Thermistor connected from analog input to ground.
            reading = self.series_resistor / (65535.0 / self.pin.value - 1.0)
        return reading

    @property
    def temperature(self) -> float:
        """The temperature of the thermistor in Celsius"""
        steinhart = self.resistance / self.nominal_resistance  # (R/Ro)
        steinhart = math.log(steinhart)  # ln(R/Ro)
        steinhart /= self.b_coefficient  # 1/B * ln(R/Ro)
        steinhart += 1.0 / (self.nominal_temperature + 273.15)  # + (1/To)
        steinhart = 1.0 / steinhart  # Invert
        steinhart -= 273.15  # convert to C

        return steinhart
