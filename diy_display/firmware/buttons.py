import digitalio
import thisbutton as tb

class Buttons(object):
    def __init__(self, power_pin, left_pin, right_pin, lights_pin, switch_pin):

        self._power_button = False
        self._power_button_long_press = False
        self._left_button = False
        self._right_button = False
        self._lights_button = False
        self._switch_button = False

        self._power = tb.thisButton(power_pin, True)
        self._power.setDebounceThreshold(20)
        self._power.assignClick(self._power_button_click_callback)
        self._power.assignLongPressStart(self._power_button_long_click_callback)
        self._left = tb.thisButton(left_pin, True)
        self._left.setDebounceThreshold(20)
        self._left.assignClick(self._left_button_click_callback)
        self._right = tb.thisButton(right_pin, True)
        self._right.setDebounceThreshold(20)
        self._right.assignClick(self._right_button_click_callback)
        self._lights = tb.thisButton(lights_pin, True)
        self._lights.setDebounceThreshold(20)
        self._lights.assignClick(self._lights_button_click_callback)
        self._switch = tb.thisButton(switch_pin, True)
        self._switch.setDebounceThreshold(20)
        self._switch.assignClick(self._switch_button_click_callback)

    def _power_button_click_callback(self):
      print("p")
      self._power_button = not self._power_button

    def _power_button_long_click_callback(self):
      self._power_button_long_press = not self._power_button_long_press

    def _left_button_click_callback(self):
      print("l")
      self._left_button = not self._left_button

    def _right_button_click_callback(self):
      print("r")
      self._right_button = not self._right_button

    def _lights_button_click_callback(self):
      print("lights")
      self._lights_button = not self._lights_button

    def _switch_button_click_callback(self):
      print("s")
      self._switch_button = not self._switch_button

    def tick(self):
       self._power.tick()
       self._left.tick()
       self._right.tick()
       self._lights.tick()
       self._switch.tick()

    @property
    def power(self):
        return self._power_button
    
    @property
    def power_long_press(self):
        return self._power_button_long_press

    @property
    def left(self):
        return self._left_button

    @property
    def right(self):
        return self._right_button
    
    @property
    def lights(self):
        return self._lights_button

    @property
    def switch(self):
        return self._switch_button