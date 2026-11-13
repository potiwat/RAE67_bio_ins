"""ดูค่าเซนเซอร์สด -- รันบน REPL:  import tools.sense
ไม่สั่งเซอร์โว ไม่ต้องเปิดไฟเซอร์โว

อัลตร้าโซนิค: ยื่นมือเข้า-ออกหน้าเซนเซอร์ ดูว่า dist เปลี่ยนตามไหม
ความชื้น: ช่วงแรกวางเซนเซอร์แห้ง (ค่าแรก = "แห้ง") -> จุ่มน้ำ ~5 วิ -> ยกออก
กด Ctrl-C เมื่อพอ แล้วมันจะบอกค่า dry/wet ที่ต้องใส่ใน config.py
"""
import time

import config as cfg
from moisture import make_moisture
from ultrasonic import make_ultrasonic


def _fmt_m(v):
    return " ---- " if v is None else "%5.2fm" % v


def run(seconds=120, every_ms=300):
    m = make_moisture(cfg)
    u = make_ultrasonic(cfg)
    if m is None and u is None:
        print("ยังไม่ได้ตั้งขาเซนเซอร์ใน config.py")
        return
    if m is not None:
        m.period_ms = 0
        print("ความชื้น: ช่วงที่ใช้อยู่ dry=%d wet=%d" % (cfg.MOIST_DRY_RAW, cfg.MOIST_WET_RAW))
    dry, far = None, None
    t0 = time.ticks_ms()
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < seconds * 1000:
            line = ""
            if u is not None:
                for _ in range(3):                      # ยิงหลายครั้งให้ตัวกรองทำงาน
                    u.poll(time.ticks_ms())
                    time.sleep_ms(cfg.US_PERIOD_MS)
                line += "dist=%s raw=%s  " % (_fmt_m(u.dist), _fmt_m(u.raw_m))
            if m is not None:
                m.poll(time.ticks_ms())
                raw = m.raw
                if raw is None:
                    line += "moist: อ่านไม่ได้"
                else:
                    if dry is None:
                        dry = raw
                    if far is None or abs(raw - dry) > abs(far - dry):
                        far = raw
                    line += "moist raw=%5d wet=%.2f |%-20s|" % (raw, m.wet, "#" * int(m.wet * 20))
            print(line)
            time.sleep_ms(every_ms)
    except KeyboardInterrupt:
        pass
    print()
    if u is not None:
        print("อัลตร้าโซนิค: ยิงพลาด %d ครั้ง" % u.bad)
    if m is None:
        return
    if dry is None or far is None or abs(far - dry) < 2000:
        print("ความชื้นแทบไม่เปลี่ยน (dry=%s ไกลสุด=%s) -- เช็คสาย AO/VCC และจุ่มให้ขาลงน้ำจริง" % (dry, far))
        return
    print("ใส่ค่านี้ใน config.py แล้วส่งขึ้นบอร์ด:")
    print("  MOIST_DRY_RAW = %d" % dry)
    print("  MOIST_WET_RAW = %d" % far)


run()
