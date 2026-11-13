import sys,types,unittest
from unittest.mock import Mock,patch
from .inputs import SampledButton


class Tests(unittest.TestCase):
 def test_gpio_callbacks_are_disabled_before_polling_and_factory_teardown(self):
  pin=types.SimpleNamespace(when_changed=object());device=types.SimpleNamespace(pin=pin,is_active=False)
  factory=Mock();device.close=Mock(side_effect=lambda:self.assertIsNone(pin.when_changed))
  def start(source,read):self.assertIsNone(pin.when_changed);self.assertFalse(read())
  with patch.dict(sys.modules,{'gpiozero':types.SimpleNamespace(DigitalInputDevice=Mock(return_value=device)),
        'gpiozero.pins.lgpio':types.SimpleNamespace(LGPIOFactory=Mock(return_value=factory))}),patch.object(SampledButton,'start_sampling',start),patch.object(SampledButton,'stop_sampling'):
   b=SampledButton(.06);b.close()
  device.close.assert_called_once();factory.close.assert_called_once()


if __name__=='__main__':unittest.main()
