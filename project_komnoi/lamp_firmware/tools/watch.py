"""ดูตำแหน่งเซอร์โวตัวเดียวแบบสด (ปลดแรงบิด ไม่สั่งขยับ) -- รันบน REPL:
    import tools.watch            # ค่าเริ่มต้น = elbow (ID 7)
    tools.watch.run(2)            # ตัวอื่น (ต้อง Ctrl-D รีเซ็ตก่อน import ซ้ำ หรือเรียก run ตรงๆ)
ขยับข้อต่อด้วยมือช้าๆ แล้วดูว่า tick เปลี่ยนตามอย่างต่อเนื่องไหม ; Ctrl-C เพื่อจบ
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def run(sid=7, seconds=60):
    for j in cfg.JOINTS:                 # ปลดแรงบิดทุกตัว กันตัวที่ค้างแรงอยู่ดึงไฟจนบัสตก
        try:
            bus.torque(j[1], False)
        except Exception:
            pass
    name = [j[0] for j in cfg.JOINTS if j[1] == sid]
    print("ปลดแรงบิดทุกข้อต่อแล้ว -- ประคองแขนไว้")
    print("ดู ID %d (%s) -- ขยับด้วยมือช้าๆ ; Ctrl-C จบ" % (sid, name[0] if name else "?"))
    lo = hi = None
    last = None
    try:
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < seconds * 1000:
            f = None
            try:
                f = bus.feedback(sid)
            except Exception:
                pass
            if f is None:
                print("  อ่านไม่ได้")
            else:
                t = f["tick"]
                lo = t if lo is None else min(lo, t)
                hi = t if hi is None else max(hi, t)
                jump = "" if last is None or abs(t - last) < 150 else "   << กระโดด %+d" % (t - last)
                last = t
                print("  tick %4d  (ต่ำสุด %4d สูงสุด %4d)  volt %.1f  temp %d%s"
                      % (t, lo, hi, f["volt"], f["temp"], jump))
            time.sleep_ms(250)
    except KeyboardInterrupt:
        pass
    print("จบ")


run()
