import displayio
from adafruit_display_shapes.line import Line
import displayio
import vectorio

palette_white = displayio.Palette(1)
palette_white[0] = 0x000000  # background

palette_black = displayio.Palette(1)
palette_black[0] = 0xFFFFFF  # fill

soc_bar_width = 8
soc_bar_height = 11

class BatterySOCWidget(object):
    def __init__(self, display_group, display_width, display_height):
        self._d_group = display_group
        self._d_width = display_width
        self._d_height = display_height
        
    
    def draw_contour(self):
        l1 = Line(0, self._d_height-1, 0, self._d_height-1-14, color=palette_black[0])
        l2 = Line(0, self._d_height-1-14, 0+34+4, self._d_height-1-14, color=palette_black[0])
        l3 = Line(0+34+4, self._d_height-1-14, 0+34+4, self._d_height-1-14+3, color=palette_black[0])
        l4 = Line(0+34+4, self._d_height-1-14+3, 0+34+4+6, self._d_height-1-14+3, color=palette_black[0])
        l5_1 = Line(0+34+4+7, self._d_height-1-14+4, 0+34+4+7, self._d_height-1-14+4, color=palette_black[0])
        l5 = Line(0+34+4+8, self._d_height-1-14+5, 0+34+4+8, self._d_height-1-14+5+4, color=palette_black[0])
        l5_2 = Line(0+34+4+7, self._d_height-1-14+5+5, 0+34+4+7, self._d_height-1-14+5+5, color=palette_black[0])
        l6 = Line(0+34+4+6, self._d_height-1-14+3+8, 0+34+4, self._d_height-1-14+3+8, color=palette_black[0])
        l7 = Line(0+34+4, self._d_height-1-14+3+8, 0+34+4, self._d_height-1-14+3+8+3, color=palette_black[0])
        l8 = Line(0+34+4, self._d_height-1-14+3+8+3, 0, self._d_height-1-14+3+8+3, color=palette_black[0])
        
        self._d_group.append(l1)
        self._d_group.append(l2)
        self._d_group.append(l3)
        self._d_group.append(l4)
        self._d_group.append(l5)
        self._d_group.append(l5_1)
        self._d_group.append(l5_2)
        self._d_group.append(l6)
        self._d_group.append(l7)
        self._d_group.append(l8)
    
        # initinal position
        x = 2
        y = self._d_height - soc_bar_height - 2 
    
        # bar 1
        self._fill_rectangle_1 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=soc_bar_width,
            height=soc_bar_height,
            x=x,
            y=y
        )
        
        # bar 2
        self._fill_rectangle_2 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=soc_bar_width,
            height=soc_bar_height,
            x=x + 1 + soc_bar_width,
            y=y
        )
        
        # bar 3
        self._fill_rectangle_3 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=soc_bar_width,
            height=soc_bar_height,
            x=x + (1 + soc_bar_width) * 2,
            y=y
        )
        
        # bar 4
        self._fill_rectangle_4 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=soc_bar_width,
            height=soc_bar_height,
            x=x + (1 + soc_bar_width) * 3,
            y=y
        )
    
        # bar 5
        self._fill_rectangle_5 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=soc_bar_width - 2,
            height=soc_bar_height - 6,
            x=x + (1 + soc_bar_width) * 4,
            y=y + 3
        )
        
        self._fill_rectangle_5_1 = vectorio.Rectangle(
            pixel_shader=palette_black,
            width = 1,
            height = soc_bar_height - 6 - 2,
            x=x + (1 + soc_bar_width) * 4 + soc_bar_width - 2,
            y=y + 3 + 1
        )
    
    def update(self, battery_soc):
        if battery_soc >= 20:
            if self._fill_rectangle_1 not in self._d_group:
                self._d_group.append(self._fill_rectangle_1)
        else:
            if self._fill_rectangle_1 in self._d_group:
                self._d_group.remove(self._fill_rectangle_1)
        
        if battery_soc >= 40:
            if self._fill_rectangle_2 not in self._d_group:
                self._d_group.append(self._fill_rectangle_2)
        else:
            if self._fill_rectangle_2 in self._d_group:
                self._d_group.remove(self._fill_rectangle_2)
                
        if battery_soc >= 60:
            if self._fill_rectangle_3 not in self._d_group:
                self._d_group.append(self._fill_rectangle_3)
        else:
            if self._fill_rectangle_3 in self._d_group:
                self._d_group.remove(self._fill_rectangle_3)
                
        if battery_soc >= 80:
            if self._fill_rectangle_4 not in self._d_group:
                self._d_group.append(self._fill_rectangle_4)
        else:
            if self._fill_rectangle_4 in self._d_group:
                self._d_group.remove(self._fill_rectangle_4)
                
        if battery_soc >= 90:
            if self._fill_rectangle_5 not in self._d_group:
                self._d_group.append(self._fill_rectangle_5)
                
            if self._fill_rectangle_5_1 not in self._d_group:
                self._d_group.append(self._fill_rectangle_5_1)
        else:
            if self._fill_rectangle_5 in self._d_group:
                self._d_group.remove(self._fill_rectangle_5)
            
            if self._fill_rectangle_5_1 in self._d_group:
                self._d_group.remove(self._fill_rectangle_5_1)
                
        