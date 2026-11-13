"""ตัวช่วยคาลิเบรตแบบโต้ตอบ -- ไม่ต้องก็อปโค้ด ไม่ต้องแก้ไฟล์เอง

    import tools.wizard

มันจะพาทำทีละข้อต่อ: หาว่า ID ไหนคือข้อต่ออะไร -> ตั้งจุด 0 องศา -> เช็คทิศ ->
วัดช่วงจริง แล้วบันทึกลงไฟล์ calib.py บนบอร์ดเอง (config.py จะอ่านไฟล์นี้ทับค่าเดิม)

ปุ่มที่ใช้ระหว่างจัดท่า (พิมพ์แล้วกด Enter)
    d / a       ขยับ +10 / -10 tick
    D / A       ขยับ +40 / -40 tick
    f / s       ขยับ +3 / -3 tick (ละเอียด)
    c           ตั้งตรงนี้เป็น 0 องศา
    t           ทดสอบทิศ (ขยับ +10 องศาแล้วกลับ)
    i           สลับทิศ (invert)
    m           จดขีดตรงนี้ (ปลดแรงบิดแล้วดันด้วยมือไปจนสุด แล้วกด m -- ทำทั้งสองฝั่ง)
    l           วัดช่วงอัตโนมัติ (ใช้กับข้อต่อแรงน้อย/แขนหนักไม่ได้ ใช้ m ดีกว่า)
    r           ปลดแรงบิด (จับด้วยมือได้)
    h           ล็อกค้างท่าปัจจุบัน
    n           ข้อต่อนี้เสร็จ ไปตัวถัดไป
    k           ข้ามข้อต่อนี้ (ยังไม่ตั้ง)
    q           เลิก (บันทึกเท่าที่ทำไว้)
"""
from machine import UART, Pin
import time

import config as cfg
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

TICKS_PER_DEG = cfg.TICKS_PER_DEG
TICK_MIN, TICK_MAX = cfg.TICK_MIN, cfg.TICK_MAX
CALIB_FILE = "calib.py"
MARGIN_DEG = 5.0
# ช่วงที่ยอมให้ใช้จริง แม้กลไกจะไปได้ไกลกว่า -- shoulder แรงน้อย เอนไกลแล้วยกกลับไม่ขึ้น
USE_CAP = {"yaw": (-90, 90), "shoulder": (-80, 30), "elbow": (-39, 172)}

# ชื่อข้อต่อเรียงจากฐานขึ้นไปหัว พร้อมค่าตั้งต้นของ max_rate กับ load_limit
# load_limit ตั้งสูงกว่าโหลดตอนทำงานปกติพอสมควร ไม่งั้นระบบจะเข้าโหมด Protect เอง
# (วัดจริงตอนรัน: ข้อต่อที่รับน้ำหนักแตะ 160-220 ตอนอยู่เฉยๆ)
JOINT_ORDER = (
    ("yaw",        "หมุนฐานซ้ายขวา",        240, 700),
    ("shoulder",   "ก้มเงยแขนล่าง",          200, 950),
    ("elbow",      "ก้มเงยแขนบน",            240, 800),
    ("head_pitch", "ก้มเงยหัวโคม",           300, 600),
    ("head_roll",  "เอียงหัวโคมซ้ายขวา",     320, 500),
)

_dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
bus = SCSBus(_uart, dir_pin=_dir_pin, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


# ---------------------------------------------------------------- ตัวช่วยระดับล่าง
def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def _fb(sid, tries=3):
    for _ in range(tries):
        d = bus.feedback(sid)
        if d is not None:
            return d
    return None


def _move(sid, tick, speed=120, wait_ms=1200):
    """สั่งไป tick แล้วรอจนนิ่ง คืน (tick จริง, load ตอนนิ่ง, ถึงเป้าไหม)"""
    tick = int(_clamp(tick, TICK_MIN, TICK_MAX))
    bus.torque(sid, True)
    bus.write_word(sid, ADDR_GOAL_SPEED, speed)
    bus.write_word(sid, ADDR_GOAL_POSITION, tick)
    last, still, fb = None, 0, None
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < wait_ms:
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
    if fb is None:
        return None, 0, False
    return fb["tick"], fb["load"], abs(fb["tick"] - tick) <= 4


def _scan(max_id=20):
    return [s for s in range(1, max_id + 1) if bus.ping(s) is not None]


def _ask(prompt):
    try:
        return input(prompt)
    except KeyboardInterrupt:
        return "q"


# ---------------------------------------------------------------- ขั้นตอนย่อย
def _identify(ids):
    """ขยับทีละตัวให้ดู แล้วให้คนบอกว่าเป็นข้อต่ออะไร -> คืน {ชื่อ: id}"""
    print("\n=== ขั้นที่ 1: ดูว่า ID ไหนคือข้อต่ออะไร ===")
    print("เจอ ID:", ids)
    print("ชื่อข้อต่อที่ใช้ได้:", ", ".join(n for n, _, _, _ in JOINT_ORDER))
    mapping = {}
    for sid in ids:
        fb = _fb(sid)
        if fb is None:
            print("ID %d อ่านค่าไม่ได้ ข้าม" % sid)
            continue
        while True:
            print("\n-- ID %d (ตอนนี้ tick %d) --" % (sid, fb["tick"]))
            cmd = _ask("กด Enter เพื่อให้มันขยับให้ดู / พิมพ์ชื่อข้อต่อ / 'k' ข้าม / 'q' เลิก : ").strip()
            if cmd == "q":
                return "quit"
            if cmd == "":
                here = _fb(sid)
                if here is None:
                    print("อ่านไม่ได้")
                    continue
                t = here["tick"]
                print("ขยับไปกลับ... ดูให้ดีว่าชิ้นไหนขยับ")
                _move(sid, t + 45, wait_ms=900)
                _move(sid, t, wait_ms=900)
                bus.torque(sid, False)
            elif cmd == "k":
                break
            elif cmd in [n for n, _, _, _ in JOINT_ORDER]:
                if cmd in mapping:
                    print("ชื่อนี้ถูกใช้โดย ID %d แล้ว" % mapping[cmd])
                    continue
                mapping[cmd] = sid
                print("บันทึก: %s = ID %d" % (cmd, sid))
                break
            else:
                print("ไม่รู้จักชื่อนี้")
    return mapping


def _tune(name, sid, desc, max_rate, load_limit):
    """จัดท่า ตั้ง center เช็คทิศ วัดช่วง -> คืน dict ของข้อต่อนี้ หรือ None ถ้าข้าม"""
    print("\n=== ข้อต่อ %s (ID %d) -- %s ===" % (name, sid, desc))
    print("จัดให้อยู่ท่าที่อยากให้เป็น 0 องศา แล้วกด c")
    fb = _fb(sid)
    if fb is None:
        print("อ่านค่าไม่ได้ ข้ามตัวนี้")
        return None
    center = fb["tick"]
    invert = False
    lo_deg, hi_deg = None, None
    mech_lo, mech_hi = None, None
    relaxed = False

    def deg(tick):
        d = (tick - center) / TICKS_PER_DEG
        return -d if invert else d

    def tick_of(d):
        return center + (-d if invert else d) * TICKS_PER_DEG

    while True:
        fb = _fb(sid)
        if fb is None:
            print("อ่านค่าไม่ได้")
            cur = center
        else:
            cur = fb["tick"]
            print("  tick=%d  deg=%.1f  load=%d  temp=%d%s"
                  % (cur, deg(cur), fb["load"], fb["temp"], "  (ปลดแรงบิดอยู่)" if relaxed else ""))
        cmd = _ask("[%s] d/a=+-10  D/A=+-40  f/s=+-3  c=ตั้ง0  t=ทดสอบทิศ  i=สลับทิศ  "
                   "m=จดขีด  r=ปลด  h=ล็อก  n=เสร็จ  k=ข้าม  q=เลิก : " % name).strip()

        if cmd in ("d", "a", "D", "A", "f", "s"):
            step = {"d": 10, "a": -10, "D": 40, "A": -40, "f": 3, "s": -3}[cmd]
            relaxed = False
            got, load, ok = _move(sid, cur + step, speed=120, wait_ms=900)
            if got is None:
                print("  สั่งไม่สำเร็จ")
            elif not ok:
                print("  ไปไม่ถึง (load %d) -- น่าจะชนขีดแล้ว" % load)
        elif cmd == "c":
            here = _fb(sid)          # อ่านใหม่ตอนกด -- ระหว่างรอพิมพ์ อาจขยับด้วยมือไปแล้ว
            if here is None:
                print("  อ่านค่าไม่ได้ ลองกด c ใหม่")
                continue
            center = here["tick"]
            print("  ตั้ง 0 องศาที่ tick %d แล้ว" % center)
        elif cmd == "t":
            relaxed = False
            # ต้องทดสอบจาก "ตำแหน่งปัจจุบัน" ไม่ใช่จาก center
            # ไม่งั้นถ้าแขนอยู่ไกลจาก center มันจะวิ่งกลับไปหา center ดูเหมือนไปทางเดิมเสมอ
            delta = 12.0 * TICKS_PER_DEG * (-1.0 if invert else 1.0)
            print("  สั่ง +12 องศา จากตรงนี้ (invert=%s) ดูว่าไปทางที่ต้องการไหม" % invert)
            got, load, ok = _move(sid, cur + delta, speed=100)
            if got is None:
                print("  สั่งไม่สำเร็จ")
                continue
            if not ok:
                print("  ไปไม่ถึง (load %d) -- ชนขีดทางนั้นแล้ว ลองขยับถอยมาก่อนแล้วกด t ใหม่" % load)
            time.sleep_ms(500)
            _move(sid, cur, speed=100)
            ans = _ask("  ไปถูกทางไหม (y/n): ").strip().lower()
            if ans == "n":
                invert = not invert
                print("  สลับทิศแล้ว invert = %s -- กด t ซ้ำเพื่อยืนยัน" % invert)
            else:
                print("  ทิศถูกแล้ว invert = %s" % invert)
        elif cmd == "i":
            invert = not invert
            print("  invert = %s (ปุ่มนี้ไม่ขยับอะไร แค่สลับค่า -- กด t เพื่อดูผล)" % invert)
        elif cmd == "m":
            here = _fb(sid)          # อ่านใหม่ตอนกด -- ค่าที่พิมพ์ก่อน prompt เป็นค่าก่อนดันด้วยมือ
            if here is None:
                print("  อ่านค่าไม่ได้ ลองกด m ใหม่")
                continue
            d = deg(here["tick"])
            if abs(d) < 3:
                print("  ยังอยู่ใกล้ 0 (%.1f) -- ดันไปให้สุดก่อนแล้วกด m" % d)
            elif d < 0:
                mech_lo = d
                print("  จดขีดฝั่งลบ = %.1f องศา" % d)
            else:
                mech_hi = d
                print("  จดขีดฝั่งบวก = %.1f องศา" % d)
            if mech_lo is not None and mech_hi is not None:
                print("  ครบสองฝั่งแล้ว: %.1f .. %.1f -- จัดกลับไปท่า 0 กด h แล้วกด n" % (mech_lo, mech_hi))
        elif cmd == "l":
            relaxed = False
            lo_deg, hi_deg = _sweep(sid, center, invert, load_limit)
        elif cmd == "r":
            bus.torque(sid, False)
            relaxed = True
            print("  ปลดแรงบิดแล้ว -- ประคองไว้ด้วย")
        elif cmd == "h":
            here = _fb(sid)
            if here:
                bus.write_word(sid, ADDR_GOAL_POSITION, here["tick"])
            bus.torque(sid, True)
            relaxed = False
            print("  ล็อกค้างท่าปัจจุบันแล้ว")
        elif cmd == "k":
            return None
        elif cmd == "q":
            return "quit"
        elif cmd == "n":
            if (mech_lo is None) != (mech_hi is None):
                print("  จดขีดไปฝั่งเดียว -- กด m อีกฝั่งก่อน")
                continue
            if mech_lo is not None:
                lo_deg, hi_deg = mech_lo + MARGIN_DEG, mech_hi - MARGIN_DEG
            if lo_deg is None:
                print("  ยังไม่ได้วัดช่วง -- ใช้ค่ากว้างๆ -60..60 ไปก่อน (กด l เพื่อวัดจริง)")
                lo_deg, hi_deg = -60.0, 60.0
            cap = USE_CAP.get(name)
            if cap:
                lo_deg, hi_deg = max(lo_deg, cap[0]), min(hi_deg, cap[1])
            print("  %s ใช้ช่วง %d .. %d องศา" % (name, int(lo_deg), int(hi_deg)))
            return {"name": name, "sid": sid, "center": center, "invert": invert,
                    "soft_min": int(lo_deg), "soft_max": int(hi_deg),
                    "max_rate": max_rate, "load_limit": load_limit}
        else:
            print("  ไม่รู้จักคำสั่งนี้")


def _home(sid, tick):
    """กลับไปจุด 0 แล้วรอจนถึงจริง -- ระยะไกลๆ ใช้เวลาหลายวินาที ห้ามเริ่มวัดฝั่งถัดไปก่อนถึง"""
    got, load, ok = _move(sid, tick, speed=120, wait_ms=6000)
    if not ok:
        print("    !! กลับไปจุด 0 ไม่ถึง (อยู่ที่ tick %s load %d) -- ผลฝั่งถัดไปอาจผิด" % (got, load))
    return ok


def _sweep(sid, center, invert, load_limit, step_deg=8.0, hard_deg=120.0):
    """ไล่หาขีดจริงทั้งสองฝั่งจากจุด 0 -- คืน (ล่าง, บน) เป็นองศา"""
    def tick_of(d):
        return center + (-d if invert else d) * TICKS_PER_DEG

    def deg_of(t):
        d = (t - center) / TICKS_PER_DEG
        return -d if invert else d

    print("  วัดช่วง... มือเตรียมตัดไฟ กด Ctrl-C ได้ถ้าท่าไม่ดี")
    out = {}
    try:
        for label, sign in (("บน", 1), ("ล่าง", -1)):
            reached = 0.0
            d = 0.0
            while abs(d) < hard_deg:
                d += sign * step_deg
                got, load, ok = _move(sid, tick_of(d), speed=120)
                if got is None:
                    break
                actual = deg_of(got)
                if not ok or abs(load) > load_limit:
                    print("    ฝั่ง%s หยุดที่ %.1f deg (load %d)" % (label, actual, load))
                    break
                reached = actual
                print("    %.1f deg  load %d" % (actual, load))
            out[sign] = reached
            _home(sid, tick_of(0.0))
    except KeyboardInterrupt:
        print("    หยุดกลางคัน")
        _home(sid, tick_of(0.0))
        for k in (1, -1):
            out.setdefault(k, 0.0)
    hi = out.get(1, 0.0) - 5.0
    lo = out.get(-1, 0.0) + 5.0
    print("  ได้ช่วงปลอดภัย %.0f .. %.0f องศา (เผื่อขอบ 5 องศาแล้ว)" % (lo, hi))
    return lo, hi


def _save(rows):
    """เขียน calib.py บนบอร์ด -- config.py จะอ่านไฟล์นี้ทับค่าเดิม"""
    order = [n for n, _, _, _ in JOINT_ORDER]
    rows = sorted(rows, key=lambda r: order.index(r["name"]) if r["name"] in order else 99)
    lines = ["# สร้างโดย tools/wizard.py -- config.py อ่านไฟล์นี้ทับค่าใน JOINTS\n",
             "JOINTS = (\n",
             "    # name          id  center invert soft_min soft_max max_rate load_limit\n"]
    for r in rows:
        lines.append('    ("%s", %d, %d, %s, %d, %d, %d, %d),\n'
                     % (r["name"], r["sid"], r["center"], r["invert"],
                        r["soft_min"], r["soft_max"], r["max_rate"], r["load_limit"]))
    lines.append(")\n")
    with open(CALIB_FILE, "w") as f:
        for ln in lines:
            f.write(ln)
    print("\nบันทึกลง %s บนบอร์ดแล้ว:" % CALIB_FILE)
    for ln in lines:
        print("  " + ln.rstrip())


def show():
    """ดูค่าที่บันทึกไว้"""
    try:
        with open(CALIB_FILE) as f:
            print(f.read())
    except OSError:
        print("ยังไม่มี %s -- รัน tools.wizard ก่อน" % CALIB_FILE)


def reset():
    """ลบค่าที่บันทึกไว้ กลับไปใช้ค่าใน config.py"""
    try:
        import os
        os.remove(CALIB_FILE)
        print("ลบ %s แล้ว" % CALIB_FILE)
    except OSError:
        print("ไม่มีไฟล์ให้ลบ")


def run():
    print("=" * 60)
    print(" ตัวช่วยคาลิเบรตโคม -- กด Ctrl-C ได้ตลอดถ้าต้องหยุด")
    print("=" * 60)
    ids = _scan()
    if not ids:
        print("ไม่เจอเซอร์โวเลย -> เช็คไฟเลี้ยง สาย และ config.PIN_TX/PIN_RX")
        return
    ids2 = _scan()
    if ids != ids2:
        print("สแกนสองครั้งได้ไม่เท่ากัน (%s กับ %s) -> สายอาจมีสัญญาณรบกวน" % (ids, ids2))

    mapping = _identify(ids)
    if mapping == "quit":
        print("ออกแล้ว ไม่ได้แก้อะไร")
        return
    if not mapping:
        print("ไม่ได้ตั้งชื่อข้อต่อเลย จบ")
        return

    print("\nสรุปที่ตั้งชื่อไว้:")
    for n, _, _, _ in JOINT_ORDER:
        if n in mapping:
            print("  %-11s = ID %d" % (n, mapping[n]))

    rows = []
    for name, desc, rate, load in JOINT_ORDER:
        if name not in mapping:
            continue
        r = _tune(name, mapping[name], desc, rate, load)
        if r == "quit":
            break
        if r:
            rows.append(r)

    if not rows:
        print("ไม่มีข้อต่อที่ตั้งเสร็จ ไม่ได้บันทึกอะไร")
        return
    done = [r["name"] for r in rows]
    missing = [n for n, _, _, _ in JOINT_ORDER if n in mapping and n not in done]
    if missing:
        print("\n!! ข้อต่อที่ยังไม่ได้ตั้ง: %s" % ", ".join(missing))
        print("   ไฟล์ที่บันทึกจะมีเฉพาะตัวที่ตั้งเสร็จ ตัวที่เหลือจะหายไปจากระบบ")
        ans = _ask("   บันทึกแค่ %d ตัวนี้เลยไหม (y/n): " % len(rows)).strip().lower()
        if ans != "y":
            print("   ไม่บันทึก -- รัน tools.wizard.run() ใหม่แล้วทำให้ครบ")
            return
    _save(rows)
    print("\nเสร็จแล้ว -- กดปุ่ม EN หรือถอดเสียบ USB เพื่อให้ค่าใหม่มีผล")


run()
