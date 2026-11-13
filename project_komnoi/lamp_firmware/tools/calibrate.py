"""หา center_tick / invert / soft limit ของแต่ละข้อต่อ -- รันบน REPL ของ ESP32

    import tools.calibrate as c
    c.ids()                 # ดูว่ามีเซอร์โว ID อะไรบ้าง
    c.relax(4)              # ปลดแรงบิด (ประคองแขนไว้ก่อน!)
    c.watch(4)              # ดู tick ขณะขยับด้วยมือ
    c.set_center(4)         # จำ tick ปัจจุบันเป็น 0 องศา
    c.check_direction(4)    # ขยับ +10 องศา ดูว่าถูกทางไหม
    c.find_limits(4)        # ไล่ไปจนชนขีดจำกัด
    c.hold_all()            # ล็อกทุกข้อต่อที่มุมปัจจุบัน
    c.relax_all()           # ปลดทุกตัว

ข้อควรระวัง
  - ตอนปลดแรงบิด แขนจะตกเพราะแรงโน้มถ่วง ให้ประคองไว้ก่อน
  - ท่าที่จับค้างไว้ตอน set_center จะกลายเป็น 0 องศาของข้อต่อนั้น
"""
from machine import UART, Pin
import time

import config as cfg
from joints import JOINT_BY_NAME, JOINT_LIST
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

_dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
bus = SCSBus(_uart, dir_pin=_dir_pin, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)

print("พร้อมคาลิเบรต -- ข้อต่อใน config.py:")
for _j in JOINT_LIST:
    print("  ID %-3d = %-11s soft %d..%d" % (_j.sid, _j.name, _j.soft_min, _j.soft_max))


def ids(max_id=20):
    found = [s for s in range(1, max_id + 1) if bus.ping(s) is not None]
    print("เจอ ID:", found)
    return found


def _joint(sid):
    for j in JOINT_LIST:
        if j.sid == sid:
            return j
    print("ID %d ไม่มีใน config.py -- ใช้ได้แค่อ่านค่า ยังสั่งมุมไม่ได้" % sid)
    return None


def relax(sid):
    bus.torque(sid, False)
    print("ปลดแรงบิด ID %d แล้ว (ประคองแขนไว้)" % sid)


def relax_all():
    for j in JOINT_LIST:
        bus.torque(j.sid, False)
    print("ปลดทุกตัวแล้ว")


def hold_all():
    for j in JOINT_LIST:
        fb = bus.feedback(j.sid)
        if fb:
            bus.write_word(j.sid, ADDR_GOAL_POSITION, fb["tick"])
        bus.torque(j.sid, True)
    print("ล็อกทุกข้อต่อที่มุมปัจจุบันแล้ว")


def read(sid):
    fb = bus.feedback(sid)
    if not fb:
        print("ID %d อ่านไม่ได้" % sid)
        return None
    j = _joint(sid)
    print("tick=%4d  deg=%s  load=%5d  temp=%d  volt=%.1f"
          % (fb["tick"], round(j.tick_to_deg(fb["tick"]), 1) if j else "-",
             fb["load"], fb["temp"], fb["volt"]))
    return fb


def watch(sid, seconds=20):
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < seconds * 1000:
        read(sid)
        time.sleep_ms(250)


def set_center(sid):
    fb = bus.feedback(sid)
    if not fb:
        print("อ่านไม่ได้")
        return None
    j = _joint(sid)
    print("\n>>> ID %d (%s): center_tick = %d"
          % (sid, j.name if j else "?", fb["tick"]))
    print(">>> เอาเลขนี้ไปใส่ใน config.py\n")
    return fb["tick"]


def goto(sid, deg, speed=300, timeout_ms=4000, quiet=False):
    """สั่งไปมุมหนึ่ง แล้ว **รอจนหยุดนิ่งจริง** ก่อนอ่านค่ากลับ
    ถ้าไปไม่ถึงเป้าหมาย = ชนขีดเชิงกล (ดูค่า load ประกอบ)"""
    j = _joint(sid)
    if j is None:
        return None
    bus.torque(sid, True)
    bus.write_word(sid, ADDR_GOAL_SPEED, speed)
    tick = j.deg_to_tick(deg)
    bus.write_word(sid, ADDR_GOAL_POSITION, tick)

    t0 = time.ticks_ms()
    last, still, peak = None, 0, 0
    fb = None
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        time.sleep_ms(60)
        fb = bus.feedback(sid)
        if fb is None:
            continue
        peak = max(peak, abs(fb["load"]))
        if last is not None and abs(fb["tick"] - last) <= 2:
            still += 1
            if still >= 4:                      # นิ่งติดกัน ~240 ms = ถึงที่แล้ว
                break
        else:
            still = 0
        last = fb["tick"]
    if fb is None:
        print("อ่านค่ากลับไม่ได้")
        return None
    actual = j.tick_to_deg(fb["tick"])
    err = actual - deg
    tag = "" if abs(err) < 3.0 else "   << ไปไม่ถึง (ต่าง %.1f deg)" % err
    if not quiet:
        print("สั่ง %6.1f -> จริง %6.1f  load %4d%s" % (deg, actual, fb["load"], tag))
    # ตัดสิน "ชน" จากโหลด "ตอนหยุดนิ่งแล้ว" ไม่ใช่โหลดสูงสุดระหว่างทาง
    # (ตอนออกตัวโหลดพุ่งเป็นปกติ ถ้าใช้ค่าสูงสุดจะหยุดตั้งแต่ก้าวแรก)
    return {"target": deg, "actual": actual, "load": fb["load"], "peak_load": peak,
            "blocked": abs(err) >= 3.0 or abs(fb["load"]) > j.load_limit}


def sweep(sid, step=10.0, settle_ms=200):
    """ไล่หาขีดจริงของข้อต่อทั้งสองฝั่งโดยอัตโนมัติ
    หยุดเมื่อไปไม่ถึงเป้าหมาย หรือโหลดสูงเกิน load_limit
    คืน (ขีดล่างจริง, ขีดบนจริง) -- เอาไปตั้ง soft_min/soft_max โดยเผื่อเข้ามา 5 องศา"""
    j = _joint(sid)
    if j is None:
        return None
    start = goto(sid, 0.0 if j.soft_min < 0 < j.soft_max else (j.soft_min + j.soft_max) / 2,
                 quiet=True)
    if start is None:
        return None
    home = start["actual"]
    out = {}
    for name, limit, sign in (("บน", j.soft_max, 1), ("ล่าง", j.soft_min, -1)):
        d, reached = home, home
        print("-- ไล่ไปทาง%s (ถึง %.0f) --" % (name, limit))
        while (d - limit) * sign < 0:
            d += sign * step
            if (d - limit) * sign > 0:
                d = limit
            r = goto(sid, d)
            if r is None:
                break
            if r["blocked"]:
                print("   หยุดที่ %.1f deg (load หยุดนิ่ง %d, สูงสุดระหว่างทาง %d)"
                      % (r["actual"], r["load"], r["peak_load"]))
                break
            reached = r["actual"]
            time.sleep_ms(settle_ms)
        out[name] = reached
        goto(sid, home, quiet=True)
    lo, hi = out["ล่าง"], out["บน"]
    print("\n>>> ID %d (%s) ไปได้จริง %.1f .. %.1f deg" % (sid, j.name, lo, hi))
    print(">>> ตั้ง soft_min = %.0f  soft_max = %.0f  (เผื่อเข้ามา 5 องศา)\n"
          % (lo + 5, hi - 5))
    return lo, hi


def nudge(sid, ticks=30, speed=120):
    """ขยับดิบๆ ด้วย tick ใช้ตอนยังไม่รู้ว่า ID ไหนคือข้อต่ออะไร"""
    fb = bus.feedback(sid)
    if not fb:
        print("อ่านไม่ได้")
        return
    here = fb["tick"]
    bus.torque(sid, True)
    bus.write_word(sid, ADDR_GOAL_SPEED, speed)
    for t in (here + ticks, here):
        bus.write_word(sid, ADDR_GOAL_POSITION, min(max(t, cfg.TICK_MIN), cfg.TICK_MAX))
        time.sleep_ms(700)
    print("ขยับ ID %d ไปกลับ %d tick แล้ว -- ข้อต่อไหนขยับ?" % (sid, ticks))


def check_direction(sid, delta=10.0):
    j = _joint(sid)
    fb = bus.feedback(sid)
    if not (j and fb):
        return
    here = j.tick_to_deg(fb["tick"])
    print("ตอนนี้ %.1f deg -- จะขยับไป %.1f deg" % (here, here + delta))
    goto(sid, here + delta)
    print("ผิดทางที่ตั้งใจ -> ตั้ง invert = True ใน config.py แล้วคาลิเบรต center ใหม่")
    goto(sid, here)


def find_limits(sid, step=5.0, pause_ms=400):
    """ค่อยๆ ไล่ไปทั้งสองฝั่งจนถึง soft limit -- มือต้องพร้อมกดปุ่มหยุด"""
    j = _joint(sid)
    fb = bus.feedback(sid)
    if not (j and fb):
        return
    start = j.tick_to_deg(fb["tick"])
    for target in (j.soft_max, j.soft_min):
        d = start
        while abs(d - target) > step:
            d += step if target > d else -step
            goto(sid, d)
            time.sleep_ms(pause_ms)
            f = bus.feedback(sid)
            if f and abs(f["load"]) > j.load_limit:
                print("โหลดสูงที่ %.1f deg (load %d) -> ตรงนี้คือขีดจริง" % (d, f["load"]))
                break
        goto(sid, start)
    print("เสร็จ -- ตั้ง soft_min/soft_max ให้แคบกว่าจุดที่โหลดเริ่มขึ้นสัก 5 องศา")
