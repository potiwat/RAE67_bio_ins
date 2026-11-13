"""โหมดสอนท่า: จับหุ่นจัดท่าทีละอารมณ์ -> จดมุมจริง -> ได้ตาราง POSES -- รันบน REPL:  import tools.teach
ต้องเปิดไฟเซอร์โว ; แรงบิดจะถูกปลด -> มือหนึ่งประคองแขนไว้ในท่า อีกมือกด Enter

ทุกท่า: จัดท่า -> Enter (จด) -> เลือกให้หุ่นค้างท่าดูได้ (y) -> Enter ปลดแรงบิด -> ท่าถัดไป
ค่าที่เกินขอบปลอดภัย (soft limit - 5 องศา) จะถูกดึงกลับและบอกให้รู้ ; yaw ตั้งเป็น 0 เสมอ (หันตามคนเอง)
Blind = ต่ำกว่า Idle นิดหน่อย, Protect = เท่า Idle (ไม่ต้องสอน)
จบแล้วพิมพ์ตาราง + บันทึก taught_poses.txt บนบอร์ด -> ส่งให้ Claude ใส่ทั้ง motion.py และ lamp.py
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus
from joints import JOINT_BY_NAME, NAMES

MARGIN = 5.0             # เผื่อขอบไว้ให้ CPG แกว่ง (ไม่กี่องศา)
ORDER = (
    ("Idle", "ยืนปกติ: แขนขาวเอนหลัง แขนเหลืองพับหน้า หัวก้มมองตรง"),
    ("Curious", "สนใจ: โน้มไปข้างหน้า เงยหน้ามองคน เอียงหัวนิดๆ"),
    ("Engage", "อบอุ่น: ก้มเข้าใกล้ หน้ามองคน"),
    ("Fear", "ตกใจ: ถอยไปข้างหลัง หดตัว หันหน้าหลบลงต่ำ"),
    ("Sleep", "หลับ: ทรุดตัวต่ำ หัวห้อยลงพื้น"),
)
_ORDER5 = ("yaw", "shoulder", "elbow", "head_pitch", "head_roll")

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


def _torque_all(on):
    for n in NAMES:
        try:
            bus.torque(JOINT_BY_NAME[n].sid, on)
        except Exception:
            pass


def _read_pose():
    """คืน {ชื่อ: องศา} ที่ดึงเข้าขอบปลอดภัยแล้ว + รายการคำเตือน ; None ถ้าอ่านไม่ได้"""
    pose, notes = {}, []
    for n in NAMES:
        j = JOINT_BY_NAME[n]
        f = _fb(j.sid)
        if f is None:
            print("  อ่าน %s ไม่ได้" % n)
            return None, None
        d = j.tick_to_deg(f["tick"])
        lo, hi = j.soft_min + MARGIN, j.soft_max - MARGIN
        if n == "yaw":
            notes.append("yaw วัดได้ %.0f -> ใช้ 0 (หันตามคนเอง)" % d)
            d = 0.0
        elif d < lo or d > hi:
            c = lo if d < lo else hi
            notes.append("%s %.0f เกินขอบปลอดภัย -> ใช้ %.0f" % (n, d, c))
            d = c
        pose[n] = int(round(d))
    return pose, notes


def _hold(pose):
    items = []
    for n in NAMES:
        j = JOINT_BY_NAME[n]
        items.append((j.sid, j.deg_to_tick(pose[n]), 100, 0))
    _torque_all(True)
    bus.sync_write_positions(items)


def _row(pose):
    return tuple(pose.get(n, 0) for n in _ORDER5)


def run():
    print("=" * 60 + "\n โหมดสอนท่า -- มือหนึ่งประคองแขน อีกมือกด Enter\n" + "=" * 60)
    _torque_all(False)
    print("ปลดแรงบิดทุกข้อต่อแล้ว")
    taught = {}
    try:
        for mode, hint in ORDER:
            while True:
                print("\n>>> %s -- %s" % (mode, hint))
                ans = input("    จัดท่าแล้วกด Enter (s = ข้ามท่านี้): ").strip().lower()
                if ans == "s":
                    break
                pose, notes = _read_pose()
                if pose is None:
                    continue
                clamped = [t for t in notes if "เกินขอบ" in t]
                for t in notes:
                    print("    - " + t)
                if clamped:
                    print("    !! มีค่าโดนดึงกลับเข้าขอบ -- ตอนค้างท่า หุ่นจะไม่เหมือนที่จัดไว้ตรงข้อต่อนั้น")
                print("    จดแล้ว: shoulder %d  elbow %d  head_pitch %d  head_roll %d"
                      % (pose["shoulder"], pose["elbow"], pose["head_pitch"], pose.get("head_roll", 0)))
                ans = input("    ให้หุ่นค้างท่านี้ดูไหม? (y = ดู / r = จัดใหม่ / Enter = ไปต่อ): ").strip().lower()
                if ans == "r":
                    continue
                if ans == "y":
                    _hold(pose)
                    input("    ค้างท่าอยู่ ดูเสร็จแล้ว *ประคองแขน* แล้วกด Enter (จะปลดแรงบิด): ")
                    _torque_all(False)
                    ans = input("    ใช้ท่านี้ไหม? (Enter = ใช้ / r = จัดใหม่): ").strip().lower()
                    if ans == "r":
                        continue
                taught[mode] = pose
                break
    except KeyboardInterrupt:
        print("\nหยุดกลางคัน -- จะพิมพ์เท่าที่สอนแล้ว")
    _torque_all(False)
    if "Idle" in taught:
        idle = taught["Idle"]
        j = JOINT_BY_NAME
        blind = dict(idle)
        blind["shoulder"] = int(max(j["shoulder"].soft_min + MARGIN, idle["shoulder"] - 3))
        blind["head_pitch"] = int(min(j["head_pitch"].soft_max - MARGIN, idle["head_pitch"] + 4))
        taught["Blind"] = blind
        taught["Protect"] = dict(idle)
    lines = []
    for mode in ("Idle", "Curious", "Engage", "Fear", "Sleep", "Blind", "Protect"):
        if mode in taught:
            lines.append('    %-10s %s,' % ('"%s":' % mode, str(_row(taught[mode]))))
    out = "\n".join(lines)
    print("\n" + "=" * 60 + "\n ตารางท่าใหม่ (yaw, shoulder, elbow, head_pitch, head_roll)\n" + "=" * 60)
    print(out)
    try:
        with open("taught_poses.txt", "w") as f:
            f.write(out + "\n")
        print("\nบันทึกไว้ที่ taught_poses.txt แล้ว -- ส่งให้ Claude ได้เลย")
        print("(อ่านจากคอม: mpremote connect COM5 fs cat taught_poses.txt)")
    except Exception as e:
        print("บันทึกไฟล์ไม่ได้: %s -- ก็อปตารางข้างบนแทน" % e)
    print("แรงบิดปลดอยู่ -- ประคองแขน")


run()
