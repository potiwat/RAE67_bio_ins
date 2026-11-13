"""ทดสอบทุกอย่างในคำสั่งเดียว -- รันบน REPL:  import tools.all
ไม่สั่งเซอร์โว ไม่ต้องเปิดไฟเซอร์โว ; อะไรยังไม่ได้ต่อก็ข้ามไปเอง

ช่วง 1: ไฟวงแหวนไล่ทีละเม็ด (นับเม็ด) แล้วแดง/เขียว/น้ำเงิน (กด Ctrl-C ข้ามได้)
ช่วง 2: ทดสอบสด -- ไฟวงแหวนตอบสนองทันที
   ยื่นมือเข้าใกล้อัลตร้าโซนิค  -> ไฟสว่างขึ้นและอุ่นขึ้น (ไม่เห็นอะไร = เทาหรี่)
   จุ่มเซนเซอร์ความชื้นลงน้ำ    -> ไฟเป็นสีฟ้า (ป่วย)
   กดปุ่ม keypad                -> ไฟกะพริบขาว
กด Ctrl-C เพื่อจบ แล้วมันจะสรุปผลให้
"""
import time

import config as cfg
from led import COOL, WARM

B_MAX = min(getattr(cfg, "LED_MAX", 0.3), 0.3)


def _try(name, fn):
    try:
        return fn()
    except Exception as e:
        print("  %s: ใช้ไม่ได้ (%s)" % (name, e))
        return None


def _ring():
    from machine import Pin
    from neopixel import NeoPixel
    return NeoPixel(Pin(cfg.PIN_LED, Pin.OUT), getattr(cfg, "LED_COUNT", 16))


def _show(np, rgb, b):
    if np is None:
        return
    b = min(max(b, 0.0), B_MAX)
    np.fill(tuple(int(c * b) for c in rgb))
    np.write()


def _ring_intro(np):
    print("\n[1] ไฟวงแหวน -- นับว่ามีกี่เม็ด (Ctrl-C ข้าม)")
    try:
        for i in range(len(np)):
            np.fill((0, 0, 0))
            np[i] = (int(255 * B_MAX),) * 3
            np.write()
            print("   เม็ด", i + 1)
            time.sleep_ms(200)
        for name, rgb in (("แดง", (255, 0, 0)), ("เขียว", (0, 255, 0)), ("น้ำเงิน", (0, 0, 255))):
            print("   ", name)
            _show(np, rgb, B_MAX)
            time.sleep_ms(1000)
    except KeyboardInterrupt:
        print("   ข้าม")
    _show(np, (0, 0, 0), 0)


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def run():
    print("=" * 56)
    print(" ทดสอบไฟ + อัลตร้าโซนิค + ความชื้น + keypad")
    print("=" * 56)
    from moisture import make_moisture
    from ultrasonic import make_ultrasonic
    from keypad import make_keypad
    np = _try("ไฟวงแหวน", _ring) if getattr(cfg, "LED_TYPE", "") == "neopixel" else None
    u = _try("อัลตร้าโซนิค", lambda: make_ultrasonic(cfg))
    m = _try("ความชื้น", lambda: make_moisture(cfg))
    k = _try("keypad", lambda: make_keypad(cfg))
    print("  พร้อม: ไฟ=%s อัลตร้าโซนิค=%s ความชื้น=%s keypad=%s"
          % tuple("มี" if x is not None else "-" for x in (np, u, m, k)))

    if np is not None:
        _ring_intro(np)
    if m is not None:
        m.period_ms = 300

    print("\n[2] ทดสอบสด -- ยื่นมือ / จุ่มน้ำ / กดปุ่ม ; Ctrl-C เพื่อจบ")
    shots = good = 0
    dmin = dmax = None
    dry = far = None
    keys = []
    flash_until = 0
    last_print = 0
    try:
        while True:
            now = time.ticks_ms()
            if u is not None and u.poll(now):
                shots += 1
                if u.raw_m is not None:
                    good += 1
                if u.dist is not None:
                    dmin = u.dist if dmin is None else min(dmin, u.dist)
                    dmax = u.dist if dmax is None else max(dmax, u.dist)
            if m is not None and m.poll(now) and m.raw is not None:
                dry = m.raw if dry is None else dry
                if far is None or abs(m.raw - dry) > abs(far - dry):
                    far = m.raw
            if k is not None:
                key = k.poll(now)
                if key is not None:
                    pair = k.scan_pair()
                    keys.append(key)
                    flash_until = time.ticks_add(now, 200)
                    print("  >> ปุ่ม %s  (ขา %s)" % (key, "-" if pair is None else "%d-%d" % pair))

            # ไฟตอบสนอง
            if time.ticks_diff(flash_until, now) > 0:
                _show(np, (255, 255, 255), B_MAX)
            else:
                wet = m.wet if (m is not None and m.wet is not None) else 0.0
                d = u.dist if u is not None else None
                if d is None:
                    rgb, b = (120, 120, 120), 0.04
                else:
                    near = min(max((1.2 - d) / 1.0, 0.0), 1.0)      # 1.2 m -> 0 , 0.2 m -> 1
                    rgb, b = _mix(COOL, WARM, near), 0.05 + near * (B_MAX - 0.05)
                if wet > 0.5:
                    rgb, b = (40, 120, 255), B_MAX               # ป่วย = ฟ้าชัดๆ ไม่ขึ้นกับระยะ
                _show(np, rgb, b)

            if time.ticks_diff(now, last_print) >= 500:
                last_print = now
                line = ""
                if u is not None:
                    line += "ระยะ %s  " % ("  ---  " if u.dist is None else "%.2f m" % u.dist)
                if m is not None:
                    line += "ความชื้น %s" % ("---" if m.wet is None else "%.2f (raw %d)" % (m.wet, m.raw))
                if line:
                    print("  " + line)
            time.sleep_ms(5)
    except KeyboardInterrupt:
        pass
    _show(np, (0, 0, 0), 0)

    print("\n" + "=" * 56 + "\n สรุป\n" + "=" * 56)
    if u is not None:
        pct = 100 * good // shots if shots else 0
        print(" อัลตร้าโซนิค: ยิง %d ครั้ง ได้ค่า %d%%  ระยะที่เห็น %s .. %s m"
              % (shots, pct, "-" if dmin is None else "%.2f" % dmin, "-" if dmax is None else "%.2f" % dmax))
    if m is not None:
        if dry is None or far is None or abs(far - dry) < 2000:
            print(" ความชื้น: ค่าแทบไม่เปลี่ยน (dry=%s ไกลสุด=%s) -- จุ่มน้ำแล้วหรือยัง?" % (dry, far))
        else:
            print(" ความชื้น: MOIST_DRY_RAW = %d   MOIST_WET_RAW = %d" % (dry, far))
    if k is not None:
        print(" keypad: กด %d ครั้ง %s" % (len(keys), " ".join(keys[-20:])))
    if np is not None:
        print(" ไฟวงแหวน: บอกเลขเม็ดสุดท้ายที่ติด และสีตรงกับที่จอบอกไหม")


run()
