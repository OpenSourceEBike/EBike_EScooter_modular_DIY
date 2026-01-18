try:
    import esp32
except ImportError:
    esp32 = None


class Mode:
    NR_MODES = 2
    THROTTLE_ZERO_MAX = 50
    THROTTLE_FULL_MIN = 950
    
    def __init__(self, brake, throttle, vars, save_to_nvs=True):
        self._brake = brake
        self._throttle = throttle
        self._vars = vars
        self._state = 0
        self._nvs = None
        self._nvs_key = "mode"
        self._save_to_nvs = save_to_nvs
        if esp32 is not None and self._save_to_nvs:
            try:
                self._nvs = esp32.NVS("diy_main_board")
            except Exception:
                self._nvs = None
        self._load_mode()

    def _load_mode(self):
        if self._nvs is None:
            return
        try:
            mode = self._nvs.get_i32(self._nvs_key)
        except Exception:
            return
        if 0 <= mode < self.NR_MODES:
            self._vars.mode = mode

    def _save_mode(self):
        if self._nvs is None:
            return
        try:
            self._nvs.set_i32(self._nvs_key, int(self._vars.mode))
            self._nvs.commit()
        except Exception:
            pass

    def tick(self):
        brake_pressed = bool(self._brake.value)
        _, throttle_value = self._throttle.value

        if self._state == 0:
            if brake_pressed and throttle_value <= self.THROTTLE_ZERO_MAX:
                self._state = 1
        
        elif self._state == 1:
            if not brake_pressed:
                self._state = 0
                
            elif throttle_value >= self.THROTTLE_FULL_MIN:
                self._vars.mode = (self._vars.mode + 1) % self.NR_MODES
                self._save_mode()
                self._state = 0
