import digitalio
import thisbutton as tb

class Buttons(object):
    def __init__(self, power_pin, up_pin, down_pin):

        self._power_button = False
        self._power_button_long_press = False
        self._up_button = False
        self._down_button = False

        self._power = tb.thisButton(power_pin, True)
        self._power.setDebounceThreshold(20)
        self._power.assignClick(self._power_button_click_callback)
        self._power.assignLongPressStart(self._power_button_long_click_callback)
        self._up = tb.thisButton(up_pin, True)
        self._up.setDebounceThreshold(20)
        self._up.assignClick(self._up_button_click_callback)
        self._down = tb.thisButton(down_pin, True)
        self._down.setDebounceThreshold(20)
        self._down.assignClick(self._down_button_click_callback)

    def _power_button_click_callback(self):
      self._power_button = not self._power_button

    def _power_button_long_click_callback(self):
      self._power_button_long_press = not self._power_button_long_press

    def _up_button_click_callback(self):
      self._up_button = not self._up_button

    def _down_button_click_callback(self):
      self._down_button = not self._down_button
      
    def tick(self):
       self._power.tick()
       self._up.tick()
       self._down.tick()

    @property
    def power(self):
        return self._power_button
    
    @property
    def power_long_press(self):
        return self._power_button_long_press

    @property
    def up(self):
        return self._up_button

    @property
    def down(self):
        return self._down_button
    