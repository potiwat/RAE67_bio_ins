"""สั่ง head_roll (ID 1) เอียงซ้าย-ขวาให้เห็นชัด -- รันบน REPL:  import tools.rollswing
ต้องเปิดไฟเซอร์โว ; มือจับสวิตช์ไว้

ไปกลางช่วงที่หมุนมือได้ (tick 120..631 -> กลาง ~375) แล้วแกว่ง +-75 tick (~22 องศา) 3 รอบ
ติดจริง (load > 500 ค้าง 0.3 วิ + ไม่ขยับ) หรือร้อนเกิน 45C -> ปลดแรงบิด ; จบแล้วปลดแรงบิดเสมอ
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

SID = 1
MID = 375
SWING = 75
LOAD_ABORT = 500
TEMP_ABORT = 45

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _fb():
    for _ in range(3):
        try:
            f = bus.feedback(SID)
            if f is not None:
                return f
        except Exception:
            pass
        time.sleep_ms(5)
    return None


def _go(goal, label, wait_ms=1500):
    """สั่งไป goal แล้วเฝ้าดู ; หยุดฉุกเฉินเมื่อ "ติดจริง" = load สูงค้าง 0.3 วิ และ tick ไม่ขยับ
    (load พุ่งแวบเดียวตอนออกตัวเป็นเรื่องปกติ ไม่นับ) ; คืน False ถ้าต้องหยุด"""
    bus.write_word(SID, ADDR_GOAL_POSITION, goal)
    t0 = time.ticks_ms()
    f = None
    path = []
    high_since, tick_at_high = None, None
    while time.ticks_diff(time.ticks_ms(), t0) < wait_ms:
        f = _fb()
        now = time.ticks_ms()
        if f is not None:
            path.append(f["tick"])
            if f["temp"] > TEMP_ABORT:
                print("  !! %s: ร้อน %d C -- ปลดแรงบิด" % (label, f["temp"]))
                return False
            if abs(f["load"]) > LOAD_ABORT:
                if high_since is None:
                    high_since, tick_at_high = now, f["tick"]
                elif (time.ticks_diff(now, high_since) > 300
                      and abs(f["tick"] - tick_at_high) < 3):
                    print("  !! %s: ติด -- load %d ค้าง และ tick ไม่ขยับ (%d) -- ปลดแรงบิด"
                          % (label, f["load"], f["tick"]))
                    print("     ทางที่ไป: %s" % path[::3])
                    return False
            else:
                high_since = None
        time.sleep_ms(50)
    if f is None:
        print("  %s: อ่านค่าไม่ได้" % label)
        return False
    ok = abs(f["tick"] - goal) <= 6
    print("  %-10s สั่ง %4d -> ได้ %4d  load %4d  temp %d  %s   ทาง: %s"
          % (label, goal, f["tick"], f["load"], f["temp"], "ok" if ok else "<< ไปไม่ถึง", path[::4]))
    return True


def run():
    print("=" * 56 + "\n head_roll เอียงซ้าย-ขวา (Ctrl-C หยุด)\n" + "=" * 56)
    if bus.ping(SID) is None:
        print("ID 1 ไม่ตอบ")
        return
    f = _fb()
    print("  เริ่มที่ tick %s" % (f["tick"] if f else "?"))
    try:
        bus.write_word(SID, ADDR_GOAL_SPEED, 150)
        bus.torque(SID, True)
        if not _go(MID, "กลาง", 2500):
            return
        for i in range(3):
            if not _go(MID + SWING, "เอียง +%d" % (i + 1)):
                return
            if not _go(MID - SWING, "เอียง -%d" % (i + 1)):
                return
        _go(MID, "กลาง")
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    finally:
        try:
            bus.torque(SID, False)
        except Exception:
            pass
        print("  ปลดแรงบิดแล้ว")


run()
