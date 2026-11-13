"""คาลิเบรต head_roll (ID 1) ตัวเดียว -- รันบน REPL:  import tools.rollcal
ไม่เขียนไฟล์อะไร: พิมพ์แถว config ออกมาให้ส่ง Claude (wizard เขียน calib.py ทับทั้งไฟล์ ข้อต่ออื่นจะหาย)
ต้องเปิดไฟเซอร์โว ; มือจับสวิตช์ไว้

[1] ปลดแรงบิด -> จับหัวให้ตั้งตรง ไม่เอียง -> Enter = จุด 0
[2] สั่งเอียงนิดเดียว -> ตอบว่าไปทางขวาของโคมไหม (ทาง + = ขวาของโคม มองจากด้านหลังโคม)
[3] ปลดแรงบิด -> เอียงด้วยมือจนสุดทีละข้าง กด Enter ทั้งสองข้าง -> ได้ช่วง (เผื่อขอบ 5 องศา, ไม่เกิน +-30)
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

SID = 1
MARGIN = 5.0
CAP = 30.0
TEST_TICKS = 30          # ~9 องศา

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _tick():
    for _ in range(5):
        try:
            f = bus.feedback(SID)
            if f is not None:
                return f["tick"], f["load"]
        except Exception:
            pass
        time.sleep_ms(10)
    return None, None


def _off():
    try:
        bus.torque(SID, False)
    except Exception:
        pass


def _goto(t, wait_ms=1200):
    bus.write_word(SID, ADDR_GOAL_POSITION, t)
    time.sleep_ms(wait_ms)
    return _tick()


def run():
    print("=" * 56 + "\n คาลิเบรต head_roll (ID 1)\n" + "=" * 56)
    if bus.ping(SID) is None:
        print("ID 1 ไม่ตอบ -- เปิดไฟเซอร์โวหรือยัง?")
        return
    try:
        _off()
        input("[1] ปลดแรงบิดแล้ว -- จับหัวให้ตั้งตรง ไม่เอียง แล้วกด Enter ")
        center, _ = _tick()
        if center is None:
            print("    อ่านค่าไม่ได้")
            return
        print("    จุด 0 = tick %d%s" % (center, "" if abs(center - 512) < 40 else
                                           "   (ห่างจาก 512 -- ตอนประกอบแกนอาจเลื่อน แต่ใช้ได้)"))

        bus.write_word(SID, ADDR_GOAL_SPEED, 120)
        bus.torque(SID, True)
        _goto(center, 600)
        got, load = _goto(center + TEST_TICKS)
        print("[2] สั่งเอียงนิดหนึ่ง (tick %d -> ได้ %s, load %s)" % (center + TEST_TICKS, got, load))
        ans = input("    หัวเอียงไปทาง \"ขวาของโคม\" (มองจากด้านหลังโคม) ใช่ไหม? (y/n): ").strip().lower()
        invert = ans != "y"
        _goto(center, 800)
        print("    invert = %s" % invert)

        _off()
        print("[3] ปลดแรงบิดแล้ว -- เอียงหัวด้วยมือช้าๆ")
        input("    เอียงไปทางขวาของโคมจนสุด ค้างไว้ แล้วกด Enter ")
        a, _ = _tick()
        input("    เอียงไปทางซ้ายของโคมจนสุด ค้างไว้ แล้วกด Enter ")
        b, _ = _tick()
        input("    จับหัวกลับมาตั้งตรง แล้วกด Enter ")
        if a is None or b is None:
            print("    อ่านค่าไม่ได้")
            return
        sign = -1.0 if invert else 1.0
        da = sign * (a - center) / cfg.TICKS_PER_DEG
        db = sign * (b - center) / cfg.TICKS_PER_DEG
        lo_m, hi_m = min(da, db), max(da, db)
        lo = max(lo_m + MARGIN, -CAP)
        hi = min(hi_m - MARGIN, CAP)
        print("    ขีดกลไก %.1f .. %.1f องศา -> ใช้ %.0f .. %.0f" % (lo_m, hi_m, lo, hi))
        if not (lo < 0 < hi):
            print("    !! ช่วงไม่คร่อม 0 -- ทำข้อ 3 ใหม่ (เอียงให้สุดทั้งสองข้าง)")
            return
        print("\nส่งบรรทัดนี้ให้ Claude:")
        print('    ("head_roll",    1,   %d,      %s,    %d,     %d,     320,     500),'
              % (center, invert, int(round(lo)), int(round(hi))))
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    finally:
        _off()
        print("ปลดแรงบิดแล้ว")


run()
