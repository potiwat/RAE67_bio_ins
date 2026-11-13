"""Sampled GPIO27 active-low input without gpiozero HoldMixin lifecycle."""
from physical_button import BufferedInput

class SampledButton(BufferedInput):
 def __init__(self,debounce_s):
  if debounce_s!=.06:raise ValueError('Unreviewed button debounce')
  super().__init__(debounce_s)
  from gpiozero import DigitalInputDevice
  from gpiozero.pins.lgpio import LGPIOFactory
  self.factory=LGPIOFactory();self.device=None
  try:
   self.device=DigitalInputDevice(27,pull_up=True,pin_factory=self.factory)
   # BufferedInput polls the level itself. An unused gpiozero edge callback
   # can outlive this gate and touch a factory already closed at handoff.
   self.device.pin.when_changed=None
   self.start_sampling(lambda:self.device.is_active)
  except BaseException:
   try:
    if self.device is not None:self.device.close()
   finally:self.factory.close()
   raise
 def close(self):
  self.stop_sampling()
  try:
   if self.device is not None:self.device.close()
  finally:self.factory.close()
