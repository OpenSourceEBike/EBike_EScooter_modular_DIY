import thisbutton as tb

class Buttons(object):
  def __init__(self, buttons_pins):

    self._power_button = False
    self._power_button_long_press = False
    self._left_button = False
    self._right_button = False
    self._lights_button = False
    self._switch_button = False

    self._nr_buttons = len(buttons_pins)

    # on current implementation 
    if self._nr_buttons != 5:
      raise Exception('on current implementation, buttons must be 5')

    self._buttons_callbacks = 2 * self._nr_buttons # 2x to accomodate a call back for click and other for long click
    self._buttons_callbacks[0] = _b0_click_callback
    self._buttons_callbacks[1] = _b0_long_click_callback
    self._buttons_callbacks[2] = _b1_click_callback
    self._buttons_callbacks[3] = None
    self._buttons_callbacks[4] = _b2_click_callback
    self._buttons_callbacks[5] = None
    self._buttons_callbacks[6] = _b3_click_callback
    self._buttons_callbacks[7] = None
    self._buttons_callbacks[8] = _b4_click_callback
    self._buttons_callbacks[9] = None

    self._buttons_state = [False] * self._nr_buttons
    self._buttons = [0] * self._nr_buttons

    for index in range(self._nr_buttons):
      self._buttons[index] = tb.thisButton(buttons_pins[index][1], True)
      self._buttons[index].setDebounceThreshold(20)
      self._buttons[index].assignClick(self._buttons_callbacks[index * 2])
      self._buttons[index].assignLongPressStart(self._buttons_callbacks[(index * 2) + 1])

  def _b0_click_callback(self):
    self._buttons_state[0] = not self._buttons_state[0]

  def _b0_long_click_callback(self):
    self._buttons_state[1] = not self._buttons_state[1]

  def _b1_click_callback(self):
    self._buttons_state[2] = not self._buttons_state[2]

  def _b2_click_callback(self):
    self._buttons_state[4] = not self._buttons_state[4]

  def _b3_click_callback(self):
    self._buttons_state[6] = not self._buttons_state[6]

  def _b4_click_callback(self):
    self._buttons_state[8] = not self._buttons_state[8]

  def tick(self):
    for index in range(self._nr_buttons):
      self._buttons[index].tick()

  @property
  def state(self, button_index):
    return (
      (1 if self._buttons_state[button_index * 2] else 0)         |
      (2 if self._buttons_state[(button_index * 2) + 1] else 0)
      )