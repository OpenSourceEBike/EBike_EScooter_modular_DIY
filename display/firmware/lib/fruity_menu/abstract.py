from displayio import Group

class AbstractMenu:
    """The base class for rendering and controlling menus"""

    _height: int = 32
    """The height in pixels of the constructed menus"""

    _width: int = 128
    """The width in pixels of the constructed menus"""

    def click(self) -> bool:
        """Clicks the currently selected item and returns whether this menu is still open (True) or close (False)"""
        pass

    def scroll(self, delta: int):
        """Update menu's selected position using the given delta and allow circular scrolling. The menu is not graphically updated."""
        pass

    def build_displayio_group(self) -> Group:
        """Builds and returns a `displayio.Group` of this menu and all its visual elements"""
        pass

class AbstractMenuOption:
    """Base class for on-screen options (buttons)"""

    text: str = ''
    """String to display in the menu"""

    upmenu = None
    """Parent menu"""

    def __init__(self, text: str):
        """Creates a menu option with the given string"""
        self.text = text

    def click(self) -> bool:
        """Interacts with the option"""
        pass