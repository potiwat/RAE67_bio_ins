"""สอนท่าหัว: ล็อกตัวโคม (ฐาน+แขน) ไว้ในท่าหนึ่ง ปล่อยหัวให้จับจัดเอง แล้วจดมุมหัว -- รันบน REPL:
    import tools.teachhead            # ค่าเริ่มต้น: ตัวท่าหลับ -> สอนหัวของท่า "แอบดู" (Peek)
ต้องเปิดไฟเซอร์โว ; ประคองแขนตอนเริ่ม (แขนจะค่อยๆ ไปท่าหลับแล้วค้างแรงบิด)
หัว (head_pitch, head_roll) จะหลวม -> จับหัวจัดให้หน้าเป็นแบบที่ต้องการ -> กด Enter
ได้บรรทัดท่าใหม่ ส่งให้ Claude
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED
from joints import JOINT_BY_NAME
from motion import POSES

BODY = ("yaw", "shoulder", "elbow")
HEAD = ("head_pitch", "head_roll")
MARGIN = 5.0

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


def run(base="Sleep", target="Peek"):
    pose = POSES[base]
    print("=" * 60 + "\n สอนหัวของท่า %s (ตัวอยู่ท่า %s)\n" % (target, base) + "=" * 60)
    input(" ประคองแขนไว้ แล้วกด Enter -- แขนจะค่อยๆ ไปท่า %s แล้วค้างไว้ " % base)
    for n in HEAD:                                   # หัวหลวม
        try:
            bus.torque(JOINT_BY_NAME[n].sid, False)
        except Exception:
            pass
    for n in BODY:                                   # ตัวค่อยๆ ไปท่าแล้วค้างแรงบิด
        j = JOINT_BY_NAME[n]
        bus.torque(j.sid, True)
        bus.write_word(j.sid, ADDR_GOAL_SPEED, 80)
        bus.write_word(j.sid, ADDR_GOAL_POSITION, j.deg_to_tick(pose[n]))
    time.sleep_ms(3000)
    print(" ตัวค้างอยู่ในท่า %s แล้ว หัวหลวมอยู่" % base)
    try:
        while True:
            input(" จับหัวจัดให้หน้าเป็นแบบที่ต้องการ (เช่น เงยมองตรง หน้าไม่เอียง) แล้วกด Enter ")
            vals = {}
            for n in HEAD:
                j = JOINT_BY_NAME[n]
                f = _fb(j.sid)
                if f is None:
                    print(" อ่าน %s ไม่ได้ ลองใหม่" % n)
                    break
                d = j.tick_to_deg(f["tick"])
                lo, hi = j.soft_min + MARGIN, j.soft_max - MARGIN
                if not lo <= d <= hi:
                    print(" !! %s %.0f เกินขอบปลอดภัย -> ใช้ %.0f" % (n, d, max(lo, min(hi, d))))
                    d = max(lo, min(hi, d))
                vals[n] = int(round(d))
            else:
                row = (int(pose["yaw"]), int(pose["shoulder"]), int(pose["elbow"]),
                       vals["head_pitch"], vals["head_roll"])
                print(" จดแล้ว: head_pitch %d  head_roll %d" % (vals["head_pitch"], vals["head_roll"]))
                print("\n ส่งบรรทัดนี้ให้ Claude:\n    \"%s\":    %s," % (target, str(row)))
                ans = input("\n Enter = จบ / r = จัดใหม่: ").strip().lower()
                if ans != "r":
                    break
    except KeyboardInterrupt:
        print(" หยุดกลางคัน")
    print(" ประคองแขนแล้วกด Ctrl-D (แขนยังค้างแรงบิดอยู่)")


run()
