import pwmio

class Buzzer(object):

    def __init__(self, buzzer_pins):
        self._buzzer_pwm_pins = []
        
        for buzzer_pin in buzzer_pins:
            self._buzzer_pwm_pins.append(pwmio.PWMOut(buzzer_pin, frequency=1000))

    @property
    def duty_cycle(self):
        value = self._buzzer_pwm_pins[0].duty_cycle / 65535.0
        if value < 0.001:
            value = 0
        
        return int(value)
            
    @duty_cycle.setter
    def duty_cycle(self, duty_cycle_percent):
        
        value = 65535 * duty_cycle_percent
        
        if value > 65535:
            value = 65535
            
        if value < 0:
            value = 0
            
        for buzzer_pwm_pin in self._buzzer_pwm_pins:
            buzzer_pwm_pin.duty_cycle = int(value)
  
