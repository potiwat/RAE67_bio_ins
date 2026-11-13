"""คาลิเบรตข้อต่อเดียว (จุด 0 + ขีดด้วยมือ) -- รันบน REPL:
    import tools.jointcal              # ค่าเริ่มต้น = elbow
    tools.jointcal.run("shoulder")     # ข้อต่ออื่น (หรือ Ctrl-D แล้ว import ใหม่)
ไม่เขียนไฟล์: พิมพ์แถว config ให้ส่ง Claude (ทิศ invert ใช้ค่าเดิมใน config -- ไม่เปลี่ยน)
ต้องเปิดไฟเซอร์โว ; แรงบิดทุกตัวจะถูกปลด -> ประคองแขน

[1] จัดข้อต่อนั้นให้อยู่ "ท่า 0" -> Enter (elbow = แขนเหลืองตั้งตรงต่อจากแขนขาว)
[2] พับ/หมุนไปทาง + จนสุด -> Enter ; ไปทาง - จนสุด -> Enter  (ได้ขีดกลไก -> ใช้ขีด - 5 องศา)
เตือนถ้าขีดเข้าใกล้ปลายช่วงอ่านของเซอร์โว (tick < 40 หรือ > 983)
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus

MARGIN = 5.0
HINT = {
    "yaw": ("หัวโคมหันตรงไปข้างหน้า", "หันซ้ายของโคม"),
    "shoulder": ("แขนขาวตั้งตรงขึ้นฟ้า", "แขนขาวเอนไปข้างหน้า"),
    "elbow": ("แขนเหลืองตั้งตรงต่อจากแขนขาว", "แขนเหลืองพับไปข้างหน้า"),
    "head_pitch": ("หัวอยู่แนวเดียวกับแขนเหลือง", "หัวก้มลง"),
    "head_roll": ("หัวตั้งตรง ไม่เอียง", "เอียงไปทางขวาของโคม"),
}

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _tick(sid):
    for _ in range(5):
        try:
            f = bus.feedback(sid)
            if f is not None:
                return f["tick"]
        except Exception:
            pass
        time.sleep_ms(10)
    return None


def run(name="elbow"):
    rows = [r for r in cfg.JOINTS if r[0] == name]
    if not rows:
        print("ไม่มี %s ใน config.JOINTS" % name)
        return
    _, sid, _c, invert, _lo, _hi, rate, load = rows[0]
    zero_hint, plus_hint = HINT.get(name, ("ท่า 0", "ทาง +"))
    print("=" * 56 + "\n คาลิเบรต %s (ID %d) -- invert=%s (ใช้ค่าเดิม)\n" % (name, sid, invert) + "=" * 56)
    for r in cfg.JOINTS:
        try:
            bus.torque(r[1], False)
        except Exception:
            pass
    print("ปลดแรงบิดทุกข้อต่อแล้ว -- ประคองแขน")
    input("[1] จัดให้ \"%s\" แล้วกด Enter " % zero_hint)
    c = _tick(sid)
    if c is None:
        print("อ่านค่าไม่ได้")
        return
    print("    จุด 0 = tick %d" % c)
    input("[2] ไปทาง \"%s\" จนสุด ค้างไว้ แล้วกด Enter " % plus_hint)
    a = _tick(sid)
    input("    ไปอีกทางจนสุด ค้างไว้ แล้วกด Enter ")
    b = _tick(sid)
    input("    จัดกลับท่า 0 แล้วกด Enter ")
    if a is None or b is None:
        print("อ่านค่าไม่ได้")
        return
    sign = -1.0 if invert else 1.0
    da = sign * (a - c) / cfg.TICKS_PER_DEG
    db = sign * (b - c) / cfg.TICKS_PER_DEG
    lo_m, hi_m = min(da, db), max(da, db)
    if not (lo_m < 0 < hi_m):
        print("    !! ขีดไม่คร่อม 0 (%.0f .. %.0f) -- ทิศ invert อาจผิด หรือจัดไม่สุด ทำใหม่" % (lo_m, hi_m))
        return
    for t in (a, b):
        if t < 40 or t > 983:
            print("    !! tick %d ชิดปลายช่วงอ่านของเซอร์โว -- ข้อต่อนี้ไปสุดทางกลไกไม่ได้อย่างปลอดภัย" % t)
    lo, hi = int(lo_m + MARGIN), int(hi_m - MARGIN)
    # ขีดต้องอยู่ในช่วงอ่านของเซอร์โวเผื่อ 15 tick
    t_lo = c + (-1 if invert else 1) * lo * cfg.TICKS_PER_DEG
    t_hi = c + (-1 if invert else 1) * hi * cfg.TICKS_PER_DEG
    for t in (t_lo, t_hi):
        if t < 15 or t > 1008:
            print("    !! ขีดที่คำนวณได้ชิดปลายช่วงอ่าน (tick %d) -- ส่งผลให้ Claude ดูก่อนใช้" % t)
    print("    ขีดกลไก %.1f .. %.1f องศา -> ใช้ %d .. %d" % (lo_m, hi_m, lo, hi))
    print("\nส่งบรรทัดนี้ให้ Claude:")
    print('    ("%s", %d, %d, %s, %d, %d, %d, %d),' % (name, sid, c, invert, lo, hi, rate, load))


run()
