from displayio import Group
from terminalio import FONT
from fruity_menu.abstract import AbstractMenu
from adafruit_displayio_sh1106 import SH1106
from adafruit_display_text.label import Label

DISPLAY = SH1106
PADDING_V_PX = 1
PADDING_H_PX = 4

class AdjustMenu(AbstractMenu):
    label: str = ''
    property = None
    on_value_set = None
    on_value_set_args = None

    def __init__(self, label: str, height: int, width: int, on_value_set = None, on_value_set_args = None):
        self.label = label
        self._width = width
        self._height = height
        self.on_value_set = on_value_set
        self.on_value_set_args = on_value_set_args

    def get_display_io_group(self) -> Group:
        pass

    def get_title_label(self):
        title = Label(FONT, padding_top=PADDING_V_PX, padding_bottom=PADDING_V_PX,padding_right=PADDING_H_PX,padding_left=PADDING_H_PX)
        title.text = self.label
        title.anchor_point = (0.5, 0)
        title.anchored_position = (self._width / 2, 0)
        
        title.color = 0x000000
        title.background_color = 0xffffff
        return title


class BoolMenu(AdjustMenu):
    """Menu for adjusting the value of a Boolean variable"""

    text_when_true = 'True'
    """Text to display when the target variable is True"""

    text_when_false = 'False'
    """Text to display when the target variable is False"""

    def __init__(self, property: bool, label: str, height: int, width: int, value_set = None,
                value_set_args = None, text_true: str = 'True', text_false: str = 'False'):
        """Instantiates a menu to adjust the value of a Boolean variable"""
        self.property = property
        self.text_when_false = text_false
        self.text_when_true = text_true
        super().__init__(label, height, width, value_set, value_set_args)

    def build_displayio_group(self):
        """Builds a `displayio.Group` that represents this menu's current state"""
        grp = Group()
        title_label = self.get_title_label()
        grp.append(title_label)

        prop_text = Label(FONT)
        if (self.property):
            prop_text.text = self.text_when_true
        else:
            prop_text.text = self.text_when_false
        prop_text.anchor_point = (0.5, 0.5)
        prop_text.anchored_position = (self._width / 2, self._height / 2)
        grp.append(prop_text)

        return grp

    def click(self):
        """Invokes the menu's stored action, if any, and returns False."""
        if (self.on_value_set is not None):
            if (self.on_value_set_args is not None):
                self.on_value_set(self.on_value_set_args, self.property)
            else:
                self.on_value_set(self.property)
        return False

    def scroll(self, delta: int):
        """Inverts the stored Boolean variable if the given delta is an odd number"""
        if delta % 2 == 1:
            self.property = not self.property
    
class NumberMenu(AdjustMenu):
    """Menu for adjusting the value of a numeric variable"""

    scroll_factor = 1
    """Multiplies the scroll delta by this number to determine how much to adjust the numeric variable"""
    
    min = None
    """Minimum allowed value"""
    
    max = None
    """Max allowed value"""

    def __init__(self, number, label: str, height: int, width: int, value_set = None,
                value_set_args = None, scroll_mulitply_factor: int = 1, min_value = None, max_value = None):
        """Instantiates a menu to adjust the value of a numeric variable"""
        self.property = number
        self.scroll_factor = scroll_mulitply_factor
        self.min = min_value
        self.max = max_value
        if (self.min is not None and self.max is not None and self.min > self.max):
            raise ValueError('Minimum allowed value is higher than the maximum allowed')
        super().__init__(label, height, width, value_set, value_set_args)

    def build_displayio_group(self):
        """Builds a `displayio.Group` that represents this menu's current state"""
        grp = Group()
        title_label = self.get_title_label()
        grp.append(title_label)

        prop_text = Label(FONT)
        prop_text.text = str(self.property)
        prop_text.anchor_point = (0.5, 0.5)
        prop_text.anchored_position = (self._width / 2, self._height / 2)
        grp.append(prop_text)
        return grp

    def click(self):
        """Invokes the menu's stored action, if any, and returns False"""
        if (self.on_value_set is not None):
            if (self.on_value_set_args is not None):
                self.on_value_set(self.on_value_set_args, self.property)
            else:
                self.on_value_set(self.property)
        return False

    def scroll(self, delta: int):
        """Increments the stored numeric variable by the delta multiplied by the scrolling factor."""
        post_scroll_value = self.property + (self.scroll_factor * delta)
        if (self.min is not None and post_scroll_value < self.min):
            self.property = self.min
        elif (self.max is not None and post_scroll_value > self.max):
            self.property = self.max
        else:
            self.property = post_scroll_value
