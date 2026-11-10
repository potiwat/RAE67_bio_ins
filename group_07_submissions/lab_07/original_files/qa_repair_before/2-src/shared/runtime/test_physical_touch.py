import unittest
from unittest.mock import patch,Mock
from physical_touch import PhysicalTouch
from physical_button import ButtonEdge

class Tests(unittest.TestCase):
    def test_active_high_gpio22_and_owned_cleanup(self):
        with patch.dict('sys.modules',{'gpiozero':Mock(),'gpiozero.pins.lgpio':Mock()}),patch.object(PhysicalTouch,'start_sampling'):
            import gpiozero
            import sys
            factory=sys.modules['gpiozero.pins.lgpio'].LGPIOFactory.return_value
            device=gpiozero.DigitalInputDevice.return_value
            t=PhysicalTouch(.06)
            gpiozero.DigitalInputDevice.assert_called_once_with(22,pull_up=False,pin_factory=factory)
            device.is_active=True
            t.sample(device.is_active,0.);t.sample(device.is_active,.1)
            self.assertFalse(t.poll(.1))
            device.is_active=False;t.sample(device.is_active,.2);t.sample(device.is_active,.3)
            device.is_active=True;t.sample(device.is_active,.4);t.sample(device.is_active,.5)
            self.assertTrue(t.poll(.5));self.assertFalse(t.poll(.8))
            t.close();device.close.assert_called_once();factory.close.assert_called_once()
