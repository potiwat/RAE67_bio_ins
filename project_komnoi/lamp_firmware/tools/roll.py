"""เช็ค head_roll (ID 1) อย่างระวัง -- รันบน REPL:  import tools.roll
ต้องเปิดไฟเซอร์โว ; มือจับสวิตช์ไว้

1) อ่านค่าขีดใน EEPROM ของเซอร์โว (ถ้าแคบ = ตัวเซอร์โวเองไม่ยอมไป)
2) ปลดแรงบิด -> หมุนหัวเอียงซ้าย-ขวาด้วยมือ ดูว่า tick เปลี่ยนตามไหม และไปได้แค่ไหน
3) (ถ้ายอม) สั่งขยับทีละนิดจากตำแหน่งปัจจุบัน ; load เกิน 500 หรือร้อนเกิน 45C -> ปลดแรงบิดทันที
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_MIN_ANGLE, ADDR_MAX_ANGLE, ADDR_MAX_TORQUE, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

SID = 1
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


def _word(addr):
    try:
        return bus.read_word(SID, addr)
    except Exception:
        return None


def _off():
    try:
        bus.torque(SID, False)
    except Exception:
        pass


def run():
    print("=" * 56 + "\n เช็ค head_roll (ID 1)\n" + "=" * 56)
    if bus.ping(SID) is None:
        print("ID 1 ไม่ตอบ -- เช็คไฟเซอร์โวและสาย")
        return
    lo, hi, tq = _word(ADDR_MIN_ANGLE), _word(ADDR_MAX_ANGLE), _word(ADDR_MAX_TORQUE)
    print("[1] EEPROM: ขีดล่าง=%s ขีดบน=%s แรงบิดสูงสุด=%s (เต็ม 1023)" % (lo, hi, tq))
    if lo is not None and hi is not None and hi - lo < 200:
        print("    !! ขีดใน EEPROM แคบมาก -- ตัวเซอร์โวเองจำกัดไว้ อาจเป็นสาเหตุที่ขยับไม่ได้")
    if tq is not None and tq < 600:
        print("    !! แรงบิดสูงสุดถูกลดไว้ -- อาจเป็นสาเหตุที่แรงไม่พอ")

    _off()
    print("\n[2] ปลดแรงบิดแล้ว -- หมุนหัวเอียงซ้าย/ขวาด้วยมือช้าๆ จนสุดทั้งสองข้าง (Ctrl-C เมื่อพอ)")
    tmin = tmax = None
    try:
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < 40000:
            f = _fb()
            if f is not None:
                t = f["tick"]
                tmin = t if tmin is None else min(tmin, t)
                tmax = t if tmax is None else max(tmax, t)
                print("    tick=%4d  (ต่ำสุด %4d สูงสุด %4d)  temp=%d" % (t, tmin, tmax, f["temp"]))
            time.sleep_ms(300)
    except KeyboardInterrupt:
        pass
    if tmin is None:
        print("    อ่านค่าไม่ได้เลย")
        return
    span = (tmax - tmin) / cfg.TICKS_PER_DEG
    print("    หมุนด้วยมือได้ tick %d..%d = ประมาณ %.0f องศา" % (tmin, tmax, span))
    if span < 5:
        print("    !! tick แทบไม่เปลี่ยน -- หมุนไม่ได้จริง หรือเฟือง/แกนติด")

    ans = input("\n[3] ลองสั่งขยับทีละนิดไหม? มือจับสวิตช์ไว้ (y/n): ").strip().lower()
    if ans != "y":
        print("ข้าม -- ส่งผลข้อ 1-2 มาให้ดูก่อน")
        return
    f = _fb()
    start = f["tick"]
    print("    เริ่มจาก tick %d" % start)
    worst = 0
    try:
        bus.torque(SID, True)
        bus.write_word(SID, ADDR_GOAL_SPEED, 80)
        for d in (10, 20, 30, -10, -20, -30, 0):
            goal = start + d
            bus.write_word(SID, ADDR_GOAL_POSITION, goal)
            time.sleep_ms(600)
            f = _fb()
            if f is None:
                print("    อ่านค่าไม่ได้ -- หยุด")
                break
            worst = max(worst, abs(f["load"]))
            ok = abs(f["tick"] - goal) <= 4
            print("    สั่ง %+3d tick -> ได้ %+3d  load %4d  temp %d  %s"
                  % (d, f["tick"] - start, f["load"], f["temp"], "ok" if ok else "<< ไปไม่ถึง"))
            if abs(f["load"]) > LOAD_ABORT or f["temp"] > TEMP_ABORT:
                print("    !! load/ความร้อนสูง -- ปลดแรงบิดทันที")
                break
    except KeyboardInterrupt:
        print("    หยุดกลางคัน")
    finally:
        _off()
    print("\nปลดแรงบิดแล้ว ; load สูงสุดที่เห็น %d -- แคปทั้งหมดส่งมาให้ดู" % worst)


run()
