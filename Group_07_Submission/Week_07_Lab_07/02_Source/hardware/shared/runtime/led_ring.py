"""One lazy SPI owner. Return LED DIN to LOW on every off/close."""
import subprocess

class LedRing:
    def __init__(self):self.pixels=None;self.spi=None
    def normal(self):
        self.show_color((255,255,255))
    def happy(self):
        self.show_color((255,180,40))
    def sleepy(self):
        self.show_color((40,100,255))
    def interested(self):
        self.show_color((255,100,0))
    def afraid(self):
        self.show_color((180,60,255))
    def angry(self):
        self.show_color((255,0,0))
    def show_color(self,color,brightness=None):
        if brightness is not None and (type(brightness) not in (int,float) or not .05<=brightness<=.08):
            raise ValueError('Demonstration LED brightness must stay between5and8percent')
        if self.pixels is None:
            import board
            import neopixel_spi
            subprocess.run(['pinctrl','set','10','a0'],check=True)
            try:
                self.spi=board.SPI()
                self.pixels=neopixel_spi.NeoPixel_SPI(self.spi,16,brightness=.03,auto_write=False,reset_time=.001)
            except BaseException:
                self.close();raise
        self.pixels.brightness=.03 if brightness is None else brightness
        self.pixels.fill(color);self.pixels.show()
    def close(self):
        try:
            if self.pixels is not None:
                try:self.pixels.fill((0,0,0));self.pixels.show()
                finally:self.pixels.deinit()
        finally:
            self.pixels=None
            try:
                if self.spi is not None:self.spi.deinit()
            finally:
                self.spi=None
                subprocess.run(['pinctrl','set','10','op','dl'],check=True)


def blackout_idle():
    """Send a black frame even without a prior LedRing owner, then hold DIN LOW."""
    ring=LedRing()
    try:
        ring.show_color((0,0,0))
    finally:
        ring.close()
