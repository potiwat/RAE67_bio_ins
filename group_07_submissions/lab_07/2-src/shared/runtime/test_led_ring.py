import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from led_ring import LedRing

class Tests(unittest.TestCase):
    def test_approved_color_and_close_returns_gpio_low_even_if_off_fails(self):
        spi=Mock();pixels=Mock();factory=Mock(return_value=pixels)
        with patch.dict(sys.modules,{'board':SimpleNamespace(SPI=lambda:spi),'neopixel_spi':SimpleNamespace(NeoPixel_SPI=factory)}),patch('led_ring.subprocess.run') as run:
            ring=LedRing();ring.sleepy()
            factory.assert_called_once_with(spi,16,brightness=.03,auto_write=False,reset_time=.001)
            pixels.fill.assert_called_with((40,100,255))
            ring.interested();pixels.fill.assert_called_with((255,100,0))
            ring.normal();pixels.fill.assert_called_with((255,255,255))
            ring.angry();pixels.fill.assert_called_with((255,0,0))
            self.assertEqual(factory.call_count,1)
            pixels.show.side_effect=RuntimeError('SPI failure')
            with self.assertRaises(RuntimeError):ring.close()
            pixels.deinit.assert_called_once();spi.deinit.assert_called_once()
            self.assertEqual(run.call_args.args[0],['pinctrl','set','10','op','dl'])
