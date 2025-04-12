import displayio
import vectorio
from adafruit_display_shapes.line import Line
from adafruit_display_shapes.arc import Arc
from utils import map_value

palette_white = displayio.Palette(1)
palette_white[0] = 0x000000  # background

palette_black = displayio.Palette(1)
palette_black[0] = 0xFFFFFF  # fill

motor_power_width = 26
motor_power_height = 18
motor_power_x = 2
motor_power_y = 0

class MotorPowerWidget(object):
    def __init__(self, display_group, display_width, display_height):
        self._d_group = display_group
        self._d_width = display_width
        self._d_height = display_height
        self._angle_previous = 0
        
        self._fill_rectangle = vectorio.Rectangle(
            pixel_shader=palette_black,
            width=motor_power_width,
            height=motor_power_height + 1,
            x=motor_power_x + motor_power_width + 9,
            y=motor_power_y
        )
        self._d_group.append(self._fill_rectangle)

        self._fill_arc = Arc(
            x=36,
            y=36,
            radius=37,
            arc_width=19,
            
            angle=90,
            direction=180+45,
            segments=8,
            outline=palette_black[0],
            fill=palette_black[0]
        )
    
    def draw_contour(self):  
        arc_1 = Arc(
            x=36,
            y=36,
            radius=37,
            arc_width=2,
            angle=-90,
            direction=90+45,
            segments=10,
            outline=palette_white[0],
            fill=palette_black[0],
        )
        
        arc_2 = Arc(
            x=36,
            y=36,
            radius=19,
            arc_width=2,
            angle=-90,
            direction=90+45,
            segments=10,
            outline=palette_white[0],
            fill=palette_black[0],
        )
            
        s_x = 0 # start_x
        s_y = 0 # start_y
        h = 35 # height
        w = 62 # width
        w_2 = int(w/2) # width

        l1 = Line(s_x, 36, 19, 36, color=palette_black[0])
        l2 = Line(w_2+5, s_y+18, w, s_y+18, color=palette_black[0])
        l3 = Line(w_2+5, s_y, w, s_y, color=palette_black[0])
        l4 = Line(w, s_y, w, s_y+18, color=palette_black[0])
        
        self._d_group.append(arc_1)
        self._d_group.append(arc_2)
        self._d_group.append(l1)
        self._d_group.append(l2)
        self._d_group.append(l3)
        self._d_group.append(l4)
    

    def update(self, motor_power_percent):
        # Limit input value
        motor_power_percent = max(0, min(motor_power_percent, 100))
        
        # Arc value
        angle = map_value(motor_power_percent, 0, 50, 0, 90)
        if angle != self._angle_previous:
            self._angle_previous = angle
            
            if self._fill_arc not in self._d_group:
                self._d_group.append(self._fill_arc)
            
            self._fill_arc.angle = -angle
        
        # Only update the rectangle width if motor power is above 50
        if motor_power_percent > 50:
            width_power = int(map_value(motor_power_percent, 50, 100, 0, motor_power_width))
            
            # Update the rectangle's width only if it changes
            if self._fill_rectangle.width != width_power:
                self._fill_rectangle.width = width_power

            if self._fill_rectangle not in self._d_group:
                self._d_group.append(self._fill_rectangle)

        # If motor power is below 50, remove the rectangle if it's in the group
        elif self._fill_rectangle in self._d_group:
            self._d_group.remove(self._fill_rectangle)
        
        
        
    