from fruity_menu.abstract import AbstractMenu, AbstractMenuOption
from fruity_menu.adjust import AdjustMenu

class ActionButton(AbstractMenuOption):
    """
    ActionButtons are used to invoke Python functions when the user clicks the button.
    For example, hooking the action to your menu's toggle function can work as an Exit button.
    """
    _action = None
    _args = None

    def __init__(self, text: str, action, args = None):
        """Creates an action button with the given title and that will execute the given action when clicked"""
        self._action = action
        self._args = args
        super().__init__(text)

    def click(self):
        """Invoke this button's stored action"""
        super().click()
        if self._args is None:
            self._action()
        else:
            self._action(self._args)
        return True
        

class SubmenuButton(AbstractMenuOption):
    """
    SubmenuButtons open nested Menus when clicked.
    """
    submenu: AbstractMenu = None
    _notify_parent = None

    def __init__(self, title: str, sub: AbstractMenu, on_open):
        self.submenu = sub
        self._notify_parent = on_open
        super().__init__(title)

    def click(self):
        super().click()
        self._notify_parent(self.submenu)
        self.submenu.show_menu()

class ValueButton(AbstractMenuOption):
    """
    ValueButtons let users modify property values.
    Only some types are supported.
    """
    target = None
    menu: AdjustMenu = None
    _notify_parent = None

    def __init__(self, title: str, value, value_menu, on_open):
        self.target = value
        self.menu = value_menu
        self._notify_parent = on_open
        super().__init__(title)

    def click(self):
        super().click()
        self._notify_parent(self.menu)