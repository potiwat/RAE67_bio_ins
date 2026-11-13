"""ทดสอบไฟวงแหวน -- รันบน REPL:  import tools.ring
ไม่สั่งเซอร์โว ไม่ต้องเปิดไฟเซอร์โว

1) ไล่จุดทีละเม็ด (นับว่ามีกี่เม็ด -> ใส่ LED_COUNT ใน config.py)
2) แดง / เขียว / น้ำเงิน (เช็คว่าลำดับสีถูก)
3) เย็น -> อุ่น ค่อยๆ เปลี่ยน (สีที่โคมจะใช้จริง)
ความสว่างไม่เกิน LED_MAX ตลอด
"""
import time

import config as cfg
from machine import Pin
from neopixel import NeoPixel
from led import COOL, WARM

N = 48                      # ยิงเผื่อไว้ วงแหวนจริงมีกี่เม็ดก็ติดเท่านั้น
B = min(getattr(cfg, "LED_MAX", 0.3), 0.3)


def _px(rgb, b=B):
    return tuple(int(c * b) for c in rgb)


def run():
    np = NeoPixel(Pin(cfg.PIN_LED, Pin.OUT), N)
    try:
        print("1) ไล่จุดทีละเม็ด -- นับว่ามีกี่เม็ด (เลขที่พิมพ์ = เม็ดที่ติดอยู่)")
        for i in range(N):
            np.fill((0, 0, 0))
            np[i] = _px((255, 255, 255))
            np.write()
            print("   เม็ด", i + 1)
            time.sleep_ms(250)
        print("2) แดง / เขียว / น้ำเงิน")
        for name, rgb in (("แดง", (255, 0, 0)), ("เขียว", (0, 255, 0)), ("น้ำเงิน", (0, 0, 255))):
            print("   ", name)
            np.fill(_px(rgb))
            np.write()
            time.sleep_ms(1200)
        print("3) เย็น -> อุ่น")
        for s in range(41):
            w = s / 40
            np.fill(_px(tuple(int(c + (wm - c) * w) for c, wm in zip(COOL, WARM))))
            np.write()
            time.sleep_ms(60)
        time.sleep_ms(800)
    except KeyboardInterrupt:
        pass
    np.fill((0, 0, 0))
    np.write()
    print("ปิดไฟแล้ว -- จำเลขเม็ดสุดท้ายที่ยังติด แล้วบอกมาเพื่อตั้ง LED_COUNT")


run()
