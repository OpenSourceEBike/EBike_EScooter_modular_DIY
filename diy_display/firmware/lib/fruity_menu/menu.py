from math import ceil, floor
from displayio import Display, Group
import terminalio
from adafruit_display_text.label import Label

from fruity_menu.adjust import AdjustMenu, BoolMenu, NumberMenu
from fruity_menu.abstract import AbstractMenu
from fruity_menu.options import ActionButton, SubmenuButton, ValueButton

OPT_HIGHLIGHT_TEXT_COLOR = 0x0000FF
"""RGB color code to use for text in selected items"""

OPT_HIGHLIGHT_BACK_COLOR = 0xFFAA00
"""RGB color code to use for the background in selected items"""

OPT_TEXT_COLOR = 0xFFAA00
"""RGB color code to use for text in UNselected items."""

OPT_BACK_COLOR = 0x0000FF
"""RGB color code to use for the background in UNselected items"""

PX_PER_LINE = 14
"""Number of pixels each line is allotted. This should roughly match the pt and scale of the font."""

SCROLL_UP_AFTER_EXIT_SUBMENU = True
"""Resets selected position in list to the first item in the list when navigating back to a menu after closing a submenu """

class Menu(AbstractMenu):
    """
    The main class for building a menu. This is what most library users should be instatiating.

    Add submenus and menu options using instance methods.

    Render the menu by passing the resulting `displayio.Group` to the display of your choosing.
    """
    
    _is_active = False
    """
    Boolean which tells whether the menu is currently Opened
    """
    
    _display: Display = None
    """
    The Display object instatiated from your driver/main. Used to access the display and controls.
    """
    
    _selection: int = 0
    """
    The 0-based index of the currently selected item
    """

    _options = []
    """
    List of menu items
    """

    _activated_submenu: AbstractMenu = None
    """
    The currently opened submenu, if any
    """
    
    _title: str = 'Menu'
    """
    Title for this menu
    """
   
    _show_title: bool = True
    """
    Whether to show Title at the top of the menu
    """

    _scroll_after_submenu: bool = True
    """
    Whether to scroll to the first item in the menu after closing a submenu
    """

    _x: int = 4
    """
    X-coordinate for rendering menu
    """

    _y: int = 0
    """
    Y-coordinate for rendering menu
    """

    def __init__(self, display: Display, height, width, show_menu_title = True, title: str = 'Menu'):
        """
        Create a Menu for the given display.
        """
        self._display = display
        if (self._display is not None):
            self._width = width
            self._height = height
        self._title = title
        self._show_title = show_menu_title
        self._options = []

    def without_display(height: int, width: int, show_menu_title = True, title: str = 'Menu'):
        """
        Create a Menu with the given width and height in pixels.
        """
        menu = Menu(None, height, width, show_menu_title, title)
        menu._width = width
        menu._height = height
        return menu

    def add_action_button(self, title: str, action, args = None) -> ActionButton:
        """
        Adds a button to this menu that invokes the given function when clicked.
        The created button is then returned.
        """
        act = ActionButton(title, action, args)
        act.upmenu = self
        self._options.append(act)
        return act

    def add_submenu_button(self, title: str, sub, add_upmenu_btn = '<- Back') -> SubmenuButton:
        """
        Adds a button to this menu that opens the given submenu when clicked.
        The created button is then returned.

        If a string is provided for `add_upmenu_btn`, the submenu will get an exit button
        which navigates up a level to this parent menu. The string will be used as the button's label.
        """
        menubut = SubmenuButton(title, sub, self._submenu_is_opening)
        if (add_upmenu_btn != '' and add_upmenu_btn != None):
            sub.add_action_button(add_upmenu_btn, self._submenu_is_closing)
        self._options.append(menubut)
        return menubut

    def add_value_button(self, title: str, value, on_value_set = None, on_set_args = None,
                         scroll_factor = 1, min_val = None, max_val = None) -> ValueButton:
        """Add a button to this menu that lets users modify the value of the given variable"""
        
        if isinstance(value, bool):
            submenu = BoolMenu(value, title, self._height, self._width, value_set=on_value_set, value_set_args=on_set_args)
        elif isinstance(value, int) or isinstance(value, float):
            submenu = NumberMenu(number=value, label=title, height=self._height, width=self._width, value_set=on_value_set,
                                 value_set_args=on_set_args, scroll_mulitply_factor=scroll_factor, min_value=min_val, max_value=max_val)
        else:
            raise NotImplementedError()
            
        val = ValueButton(title, value, submenu, self._submenu_is_opening)
        val.upmenu = self
        self._options.append(val)
        return val

    def build_displayio_group(self) -> Group:
        """Builds a `displayio.Group` of this menu and all its options and current selection."""
        self._y = 0
        grp = Group()
        if self._show_title:
            lbl = self.get_title_label()
            grp.append(lbl)

        # determine number of rows to fit on-screen
        remaining_y_px = self._height - self._y
        max_rows_per_page = floor(remaining_y_px / PX_PER_LINE)
        
        # determine the indices of the page and row for paginated display
        if (self._selection == 0):
            selected_relative_row = 0
            selected_page = 0
        else:
            selected_relative_row = self._selection % max_rows_per_page
            selected_page = floor(self._selection / max_rows_per_page)
        
        index_offset = selected_page * max_rows_per_page        

        for i in range(max_rows_per_page):
            if (i + index_offset >= len(self._options)):
                continue
            opt = self._options[i + index_offset]
            lbl = Label(terminalio.FONT)
            lbl.text = opt.text

            if i == selected_relative_row:
                lbl.color = OPT_HIGHLIGHT_TEXT_COLOR
                lbl.background_color = OPT_HIGHLIGHT_BACK_COLOR
            else:
                lbl.color = OPT_TEXT_COLOR
                lbl.background_color = OPT_BACK_COLOR
            lbl.anchor_point = (0,0)
            lbl.anchored_position = (self._x, self._y)
            grp.append(lbl)

            self._y = self._y + PX_PER_LINE
        
        return grp


    def get_title_label(self) -> Label:
        """Gets the Label for this menu's title and adjusts the builder's coordinates to compensate for the object"""
        lbl = Label(terminalio.FONT)
        lbl.text = '    ' + self._title
        lbl.color = OPT_HIGHLIGHT_TEXT_COLOR
        lbl.background_color = OPT_HIGHLIGHT_BACK_COLOR
        lbl.anchored_position = (0, self._y)
        lbl.anchor_point = (0, 0)
        self._y = self._y + PX_PER_LINE
        return lbl
    

    def show_menu(self) -> Group:
        """
        Builds the option group and renders it to the display.

        If this Menu was built without a Display object, then this function
        will return the `displayio.Group` that needs to be shown on the display.

        If this Menu was built WITH a Display object, then this function
        will also display the `Group` itself.
        """
        # if no submenu is open, then show this menu
        # print('showing', self._title)
        if self._activated_submenu is None:
            grp = self.build_displayio_group()
            self._display.show(grp)
            self._is_active = True
            return grp
        else:
            # if submenu active, then render that submenu
            # main and submenus can show themselves, but adjustmenus have to *be* shown
            if (isinstance(self._activated_submenu, AdjustMenu)):
                grp = self._activated_submenu.build_displayio_group()
                self._display.show(grp)
                return grp
            else:
                return self._activated_submenu.show_menu()

    def click(self) -> bool:
        """Clicks the currently selected item and returns whether this menu is still open (True) or closed (False)"""
        # Exec submenu if open
        if (self._activated_submenu != None):
            # AdjustMenus have to be reloaded by their parent menu
            if (isinstance(self._activated_submenu, AdjustMenu)):
                adjust_wants_to_close = not self._activated_submenu.click()
                if (adjust_wants_to_close):
                    self._submenu_is_closing()
                return True
            else:
                return self._activated_submenu.click()
        else:
            # otherwise click this menu
            selected = self._options[self._selection]
            return selected.click()
            

    def scroll(self, delta: int) -> int:
        """
        Update menu's selected position using the given delta and allowing circular scrolling.
        The menu is not graphically updated.
        This method returns the post-scroll position in the menu.
        """
        # Exec submenu if open
        if (self._activated_submenu != None):
            return self._activated_submenu.scroll(delta)
        
        # Else, scroll this menu
        if delta > 0:
            # Loop to first item if scrolling down while on last item
            if self._selection == len(self._options) - 1:
                self._selection = 0
            # Else just scroll down
            else:
                self._selection = self._selection + 1
        if delta < 0:
            # Loop to last item if scrolling up while on first item
            if self._selection == 0:
                self._selection = len(self._options) - 1
            # Else just scroll up
            else:
                self._selection = self._selection - 1
        #print('Scrolled to', self._selection, 'using delta', delta)
        return self._selection
    
    def _submenu_is_closing(self):
        if (self._scroll_after_submenu):
            self._selection = 0
        self._activated_submenu = None
        self.show_menu()

    def _submenu_is_opening(self, activated_menu):
        self._activated_submenu = activated_menu

        if (isinstance(self._activated_submenu, AdjustMenu)):
            self.show_menu()

    def create_menu(self, title: str = 'Menu'):
        """
        Create a new Menu object using this menu's properties, with an optional new title.
        This menu won't 'register' the newly created menu, just instantiate and return it.
        """
        return Menu(self._display, self._height, self._width, show_menu_title=self._show_title, title=title)
