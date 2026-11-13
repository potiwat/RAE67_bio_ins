"""หมุนแกนเซอร์โวไปจุด 0 ที่คาลิเบรตไว้ แล้วค้างไว้ให้ประกอบแขนใหม่ -- รันบน REPL:
    import tools.recenter                 # ค่าเริ่มต้น = elbow (ID 7) -> center ใน config
ใช้ตอนแขนถอดออกจากแกนแล้ว (แกนเปล่า) ; ปลดแรงบิดตัวอื่นทุกตัวก่อน กันไฟบัสตก

ประกอบแขนตามท่า 0 ของข้อต่อนั้น เช่น elbow = แขนบนตั้งตรงต่อจากแขนล่าง
แล้วค่าคาลิเบรตเดิม (center/invert/ขีด) ใช้ต่อได้เลย ไม่ต้องคาลิเบรตใหม่
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_MIN_ANGLE, ADDR_MAX_ANGLE, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

LOAD_ABORT = 500
TEMP_ABORT = 50

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _fb(sid):
    for _ in range(3):
        try:
            f = bus.feedback(sid)
            if f is not None:
                return f
        except Exception:
            pass
        time.sleep_ms(5)
    return None


def run(sid=7):
    row = [j for j in cfg.JOINTS if j[1] == sid]
    if not row:
        print("ID %d ไม่อยู่ใน config.JOINTS" % sid)
        return
    name, _, center = row[0][0], row[0][1], row[0][2]
    print("=" * 56 + "\n ตั้งแกน %s (ID %d) ไปจุด 0 = tick %d\n" % (name, sid, center) + "=" * 56)
    for j in cfg.JOINTS:
        try:
            bus.torque(j[1], False)
        except Exception:
            pass
    f = _fb(sid)
    if f is None:
        print("  ID %d อ่านค่าไม่ได้ -- เปิดไฟเซอร์โวหรือยัง?" % sid)
        return
    try:
        lo, hi = bus.read_word(sid, ADDR_MIN_ANGLE), bus.read_word(sid, ADDR_MAX_ANGLE)
    except Exception:
        lo = hi = None
    print("  ตอนนี้ tick %d  volt %.1f  temp %d  ขีด EEPROM %s..%s" % (f["tick"], f["volt"], f["temp"], lo, hi))
    if f["tick"] >= 1015 or f["tick"] <= 8:
        print("  !! ค่าอยู่ที่ปลายสุด -- หมุนแกนเปล่าด้วยมือให้ tick ออกมากลางๆ ก่อน (ใช้ tools.watch ดู) แล้วค่อยรันใหม่")
        return
    if lo is not None and hi is not None and not (lo <= center <= hi):
        print("  !! center อยู่นอกขีด EEPROM -- ส่งผลนี้ให้ Claude")
        return
    move_deg = abs(center - f["tick"]) / cfg.TICKS_PER_DEG
    print("  จะหมุนแกนจาก tick %d ไป %d = ประมาณ %.0f องศา" % (f["tick"], center, move_deg))
    if move_deg > 20:
        print("  !! หมุนไกล -- ถ้าแขนยังติดอยู่กับแกน แขนจะพับไปชนได้ ต้องถอด horn ให้หลุดฟันก่อน")
    ans = input("  แกนเปล่า ไม่มีแขนติดอยู่ ใช่ไหม? หมุนไป tick %d เลยไหม (y/n): " % center).strip().lower()
    if ans != "y":
        print("  ยกเลิก")
        return
    try:
        bus.write_word(sid, ADDR_GOAL_SPEED, 120)
        bus.torque(sid, True)
        bus.write_word(sid, ADDR_GOAL_POSITION, center)
        t0 = time.ticks_ms()
        high_since = None
        while time.ticks_diff(time.ticks_ms(), t0) < 4000:
            f = _fb(sid)
            if f is not None:
                if f["temp"] > TEMP_ABORT:
                    print("  !! ร้อน %d C" % f["temp"])
                    return
                if abs(f["load"]) > LOAD_ABORT:
                    high_since = high_since or time.ticks_ms()
                    if time.ticks_diff(time.ticks_ms(), high_since) > 300:
                        print("  !! load %d ค้าง tick %d -- ติด/วิ่งผิดทาง หยุด" % (f["load"], f["tick"]))
                        return
                else:
                    high_since = None
                if abs(f["tick"] - center) <= 3:
                    break
            time.sleep_ms(50)
        if f is None or abs(f["tick"] - center) > 3:
            print("  !! ไปไม่ถึง (ได้ %s) -- ส่งผลนี้ให้ Claude" % (f["tick"] if f else "?"))
            return
        print("  ถึงแล้ว tick %d -- ค้างแรงบิดไว้" % f["tick"])
        print("  ประกอบแขนตาม \"ท่า 0\" ของ %s แล้วขันน็อตให้แน่น" % name)
        input("  เสร็จแล้วกด Enter ...")
        f = _fb(sid)
        if f is not None:
            print("  หลังประกอบ tick %d (ควรใกล้ %d)" % (f["tick"], center))
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    finally:
        try:
            bus.torque(sid, False)
        except Exception:
            pass
        print("  ปลดแรงบิดแล้ว")


run()
