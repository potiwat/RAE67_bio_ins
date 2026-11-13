"""Verified GPIO22 active-HIGH touch; edge detection only, no motor access."""
from physical_button import BufferedInput

def reviewed_touch_debounce(value=.06):
    if type(value) not in (int,float) or value not in (.03,.06):raise ValueError('Unreviewed Touch debounce')
    return value

class PhysicalTouch(BufferedInput):
    def __init__(self,debounce_s):
        super().__init__(reviewed_touch_debounce(debounce_s))
        from gpiozero import DigitalInputDevice
        from gpiozero.pins.lgpio import LGPIOFactory
        self.factory=LGPIOFactory();self.device=None
        try:self.device=DigitalInputDevice(22,pull_up=False,pin_factory=self.factory)
        except BaseException:self.factory.close();raise
        self.start_sampling(lambda:self.device.is_active)
    def close(self):
        self.stop_sampling()
        try:
            if self.device is not None:self.device.close()
        finally:self.factory.close()
