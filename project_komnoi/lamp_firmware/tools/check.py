"""ตรวจว่าคาลิเบรตถูกไหม -- รันบน REPL:  import tools.check

ไล่ทีละข้อต่อ แล้วรายงานว่าตัวไหนผิดปกติ โดยไม่ต้องเดาเอง
  1. ค่าที่ตั้งไว้สมเหตุสมผลไหม (center อยู่ในช่วง, soft_min < soft_max)
  2. ตอนนี้อยู่ในช่วง soft ไหม
  3. สั่งไป 0 องศาแล้วไปถึงจริงไหม
  4. สั่ง +10 แล้ว tick ขยับไปทางที่ invert บอกไว้ไหม (เช็คทิศแบบอัตโนมัติ)
  5. ไปถึงขอบทั้งสองฝั่งของ soft limit ได้ไหม
  6. โหลดตอนอยู่นิ่งสูงกว่า load_limit ไหม (ถ้าสูง -> ระบบจะเข้า Protect ตลอด)

ใช้
    import tools.check            ตรวจทุกข้อต่อ
    import tools.check as k
    k.one("elbow")                ตรวจเฉพาะตัวเดียว
"""
from machine import UART, Pin
import time

import config as cfg
from joints import JOINT_LIST, JOINT_BY_NAME
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

_dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
bus = SCSBus(_uart, dir_pin=_dir_pin, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _fb(sid, tries=3):
    for _ in range(tries):
        d = bus.feedback(sid)
        if d is not None:
            return d
    return None


def _settle(sid, tick, speed=120, timeout_ms=2500):
    tick = int(min(max(tick, cfg.TICK_MIN), cfg.TICK_MAX))
    f0 = _fb(sid)
    if f0 is not None:                    # รอตามระยะทาง: speed ~ tick/วินาที (วัดจริงบน SCS15)
        timeout_ms = max(timeout_ms, int(abs(tick - f0["tick"]) * 1000 / speed) + 1500)
    bus.torque(sid, True)
    bus.write_word(sid, ADDR_GOAL_SPEED, speed)
    bus.write_word(sid, ADDR_GOAL_POSITION, tick)
    last, still, fb = None, 0, None
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        time.sleep_ms(60)
        fb = _fb(sid)
        if fb is None:
            continue
        if last is not None and abs(fb["tick"] - last) <= 2:
            still += 1
            if still >= 3:
                break
        else:
            still = 0
        last = fb["tick"]
    return fb


def one(name, move=True):
    """ตรวจข้อต่อเดียว ; move=False = ดูค่าอย่างเดียว ไม่สั่งขยับ"""
    j = JOINT_BY_NAME.get(name)
    if j is None:
        print("ไม่มีข้อต่อชื่อ %s ใน config" % name)
        return False
    print("\n=== %s (ID %d) ===" % (j.name, j.sid))
    print("  center=%d invert=%s soft=%d..%d rate=%d load_limit=%d"
          % (j.center_tick, j.invert, j.soft_min, j.soft_max, j.max_rate, j.load_limit))
    bad = []

    # 1. ค่าที่ตั้งไว้
    if not (cfg.TICK_MIN <= j.center_tick <= cfg.TICK_MAX):
        bad.append("center %d อยู่นอกช่วง tick ที่ใช้ได้" % j.center_tick)
    if j.soft_min >= j.soft_max:
        bad.append("soft_min >= soft_max")
    span = j.soft_max - j.soft_min
    if span < 15:
        bad.append("ช่วงแคบมาก (%d องศา) -- น่าจะวัดไม่ครบ" % span)
    lo_t, hi_t = j.tick_range()
    if lo_t <= cfg.TICK_MIN + 2 or hi_t >= cfg.TICK_MAX - 2:
        bad.append("ช่วง soft ชนขอบ tick (%d..%d) -- center อาจไม่อยู่กลาง" % (lo_t, hi_t))

    # 2. ตำแหน่งตอนนี้
    fb = _fb(j.sid)
    if fb is None:
        print("  อ่านค่าไม่ได้ -- เช็คสายและไฟเลี้ยง")
        return False
    here = j.tick_to_deg(fb["tick"])
    print("  ตอนนี้ tick=%d deg=%.1f load=%d temp=%d volt=%.1f"
          % (fb["tick"], here, fb["load"], fb["temp"], fb["volt"]))
    if not (j.soft_min - 2 <= here <= j.soft_max + 2):
        bad.append("ตอนนี้อยู่ที่ %.1f องศา ซึ่งอยู่นอกช่วง soft" % here)
    if abs(fb["load"]) > j.load_limit:
        bad.append("โหลดตอนนิ่ง %d เกิน load_limit %d -> ระบบจะเข้าโหมด Protect ตลอด"
                   % (abs(fb["load"]), j.load_limit))
    elif abs(fb["load"]) > j.load_limit * 0.6:
        bad.append("โหลดตอนนิ่ง %d ใกล้ load_limit %d มาก -> เสี่ยงเข้า Protect เอง"
                   % (abs(fb["load"]), j.load_limit))

    if not move:
        _report(j.name, bad)
        return not bad

    # 3. ไป 0 องศา
    mid = 0.0 if j.soft_min < 0 < j.soft_max else (j.soft_min + j.soft_max) / 2.0
    fb = _settle(j.sid, j.deg_to_tick(mid))
    if fb is None:
        bad.append("สั่งไป %.0f องศาแล้วอ่านค่ากลับไม่ได้" % mid)
        _report(j.name, bad)
        return False
    got = j.tick_to_deg(fb["tick"])
    print("  สั่ง %.0f -> จริง %.1f load %d" % (mid, got, fb["load"]))
    if abs(got - mid) > 4.0:
        bad.append("ไป %.0f องศาไม่ถึง (ได้ %.1f load %d) -- ชนกลไกหรือแรงไม่พอ"
                   % (mid, got, fb["load"]))

    # 4. ทิศ -- ต้องอ่าน tick "ตอนนิ่งแล้ว" เป็นฐาน ไม่ใช่ค่าที่อ่านมาก่อนหน้า
    fb_base = _fb(j.sid)
    if fb_base is None:
        bad.append("อ่านค่าก่อนทดสอบทิศไม่ได้")
    else:
        base_tick = fb_base["tick"]
        fb2 = _settle(j.sid, j.deg_to_tick(mid + 12.0))
        if fb2 is None:
            bad.append("ทดสอบทิศแล้วอ่านค่ากลับไม่ได้")
        else:
            d_tick = fb2["tick"] - base_tick
            want_up = not j.invert
            print("  ทิศ: จาก tick %d สั่ง +12 องศา -> tick %d (เปลี่ยน %+d, คาดว่าจะ %s)"
                  % (base_tick, fb2["tick"], d_tick, "เพิ่ม" if want_up else "ลด"))
            if abs(d_tick) < 10:
                bad.append("สั่ง +12 องศาแล้ว tick แทบไม่ขยับ (%+d) -- ติดหรือแรงไม่พอ" % d_tick)
            elif (d_tick > 0) != want_up:
                bad.append("ทิศกลับกับที่ตั้งไว้ -- ต้องสลับ invert เป็น %s" % (not j.invert))
    _settle(j.sid, j.deg_to_tick(mid))

    # 4.5 center อยู่กลางช่วงไหม (ไม่ใช่ความผิด แต่ทำให้หมุนสองข้างไม่เท่ากัน)
    off = (j.soft_min + j.soft_max) / 2.0
    if abs(off) > 15:
        print("  หมายเหตุ: จุด 0 องศาไม่ได้อยู่กลางช่วง (กลางอยู่ที่ %.0f องศา)" % off)
        print("            ไปทางหนึ่งได้ %.0f องศา อีกทาง %.0f องศา -- ใช้งานได้ แค่ไม่สมมาตร"
              % (j.soft_max, -j.soft_min))

    # 5. ขอบทั้งสองฝั่ง
    for label, target in (("บน", j.soft_max - 3.0), ("ล่าง", j.soft_min + 3.0)):
        fb3 = _settle(j.sid, j.deg_to_tick(target))
        if fb3 is None:
            bad.append("ไปขอบ%sแล้วอ่านค่าไม่ได้" % label)
            continue
        g = j.tick_to_deg(fb3["tick"])
        mark = "" if abs(g - target) <= 5.0 else "  << ไปไม่ถึง"
        print("  ขอบ%s สั่ง %.0f -> จริง %.1f load %d%s" % (label, target, g, fb3["load"], mark))
        if abs(g - target) > 5.0:
            bad.append("ไปขอบ%s (%.0f องศา) ไม่ถึง ได้แค่ %.1f load %d -- soft limit กว้างเกินจริง"
                       % (label, target, g, fb3["load"]))
        elif abs(fb3["load"]) > j.load_limit * 0.8:
            bad.append("ที่ขอบ%s โหลดสูง %d -- ควรหด soft limit เข้ามา" % (label, fb3["load"]))
        _settle(j.sid, j.deg_to_tick(mid))

    _report(j.name, bad)
    return not bad


def _report(name, bad):
    if not bad:
        print("  ผลตรวจ %s: ผ่าน" % name)
    else:
        print("  ผลตรวจ %s: มีปัญหา %d ข้อ" % (name, len(bad)))
        for b in bad:
            print("    - " + b)


def run(move=True):
    print("=" * 58)
    print(" ตรวจการคาลิเบรต -- กด Ctrl-C ได้ถ้าท่าไหนดูไม่ดี")
    print("=" * 58)
    found = [s for s in range(1, 20) if bus.ping(s) is not None]
    print("ID ที่เจอบนบัส:", found)
    cfg_ids = [j.sid for j in JOINT_LIST]
    print("ID ที่ config ใช้:", cfg_ids)
    missing = [s for s in cfg_ids if s not in found]
    extra = [s for s in found if s not in cfg_ids]
    if missing:
        print("  !! config อ้าง ID %s แต่หาไม่เจอบนบัส" % missing)
    if extra:
        print("  !! เจอ ID %s บนบัส แต่ config ไม่ได้ใช้" % extra)

    ok = []
    ng = []
    try:
        for j in JOINT_LIST:
            if one(j.name, move=move):
                ok.append(j.name)
            else:
                ng.append(j.name)
    except KeyboardInterrupt:
        print("\nหยุดกลางคัน")
    print("\n" + "=" * 58)
    print(" ผ่าน: %s" % (", ".join(ok) if ok else "-"))
    print(" มีปัญหา: %s" % (", ".join(ng) if ng else "-"))
    print("=" * 58)


run()
