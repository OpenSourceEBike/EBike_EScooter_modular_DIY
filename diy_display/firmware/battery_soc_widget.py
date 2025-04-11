import displayio
from adafruit_display_shapes.line import Line

palette_white = displayio.Palette(1)
palette_white[0] = 0x000000  # background

palette_black = displayio.Palette(1)
palette_black[0] = 0xFFFFFF  # fill

class BatterySOCWidget(object):
    def __init__(self, display_group, display_width, display_height):
        self._d_group = display_group
        self._d_width = display_width
        self._d_height = display_height
    
    def draw_contour(self):
        l1 = Line(0, self._d_height-1, 0, self._d_height-1-14, color=palette_black[0])
        l2 = Line(0, self._d_height-1-14, 0+34, self._d_height-1-14, color=palette_black[0])
        l3 = Line(0+34, self._d_height-1-14, 0+34, self._d_height-1-14+3, color=palette_black[0])
        l4 = Line(0+34, self._d_height-1-14+3, 0+34+10, self._d_height-1-14+3, color=palette_black[0])
        l5 = Line(0+34+10, self._d_height-1-14+3, 0+34+10, self._d_height-1-14+3+8, color=palette_black[0])
        l6 = Line(0+34+10, self._d_height-1-14+3+8, 0+34, self._d_height-1-14+3+8, color=palette_black[0])
        l7 = Line(0+34, self._d_height-1-14+3+8, 0+34, self._d_height-1-14+3+8+3, color=palette_black[0])
        l8 = Line(0+34, self._d_height-1-14+3+8+3, 0, self._d_height-1-14+3+8+3, color=palette_black[0])
        
        self._d_group.append(l1)
        self._d_group.append(l2)
        self._d_group.append(l3)
        self._d_group.append(l4)
        self._d_group.append(l5)
        self._d_group.append(l6)
        self._d_group.append(l7)
        self._d_group.append(l8)
    
    
    
    