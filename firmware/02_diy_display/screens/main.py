
from .base import BaseScreen
from widgets.widget_battery_soc import BatterySOCWidget
from widgets.widget_motor_power import MotorPowerWidget
from widgets.widget_text_box import WidgetTextBox
from fonts import ac437_hp_150_re_12 as font_small, freesans20 as font, freesansbold50 as font_big

class MainScreen(BaseScreen):
    NAME = "Main"
    
    def on_enter(self):
        self.clear()
        
        motor_power_widget = MotorPowerWidget(self.fb, self.fb.width, self.fb.width)
        motor_power_widget.update(0)
        
        battery_soc_widget = BatterySOCWidget(self.fb, self.fb.width, self.fb.width)
        battery_soc_widget.draw_contour()
        battery_soc_widget.update(0)

        wheel_speed_widget = WidgetTextBox(self.fb, self.fb.width, self.fb.width,
                                            font=font_big,
                                            left=0, top=2, right=1, bottom=0,
                                            align_inside="right",
                                            debug_box=False)
        wheel_speed_widget.set_box(x1=self.fb.width - 55, y1=0, x2=self.fb.width - 1, y2=36)
        wheel_speed_widget.update(0)

        warning_widget = WidgetTextBox(self.fb, self.fb.width, self.fb.width,
                                        font=font_small,
                                        align_inside="left")
        warning_widget.set_box(x1=0, y1=38, x2=63, y2=38+9)
        warning_widget.update('')

        clock_widget = WidgetTextBox(self.fb, self.fb.width, self.fb.width,
                                        font=font,
                                        align_inside="right")
        clock_widget.set_box(x1=self.fb.width-52, y1=self.fb.width-17, x2=self.fb.width-3, y2=self.fb.width-2)
        clock_widget.update('')

    def render(self):
        pass
