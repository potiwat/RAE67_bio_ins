"""เช็คเซอร์โวเร็วๆ ว่าตอบกี่ตัว (อ่านอย่างเดียว ไม่สั่งขยับ ไม่ยุ่งแรงบิด) -- รันบน REPL:
    import tools.servos
    tools.servos.run()          # รันซ้ำ (หรือ Ctrl-D แล้ว import ใหม่)
    tools.servos.run(scan=True) # สแกน ID 0..30 เพิ่ม หาเซอร์โวแปลกปลอม/ID ผิด (~1 วิ)
ต้องเปิดไฟเซอร์โว ; ถ้าโคมกำลังทำงาน (main.py) ให้ Ctrl-C ก่อน
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _fb(sid, tries=3):
    for _ in range(tries):
        try:
            f = bus.feedback(sid)
            if f is not None:
                return f
        except Exception:
            pass
        time.sleep_ms(5)
    return None


def _deg(row, tick):
    _, _, center, invert, _lo, _hi, _r, _l = row
    d = (tick - center) / cfg.TICKS_PER_DEG
    return -d if invert else d


def run(scan=False):
    rows = cfg.JOINTS
    print("=" * 66)
    print(" เซอร์โวของโคม (%d ข้อต่อใน config) -- อ่านอย่างเดียว" % len(rows))
    print("=" * 66)
    print(" %-11s %3s  %-6s %5s %7s %6s %5s %6s" % ("ข้อต่อ", "ID", "สถานะ", "tick", "องศา", "volt", "C", "load"))
    ok, volts, warn = 0, [], []
    for row in rows:
        name, sid, _c, _inv, lo, hi = row[0], row[1], row[2], row[3], row[4], row[5]
        f = _fb(sid)
        if f is None:
            print(" %-11s %3d  %-6s" % (name, sid, "ไม่ตอบ"))
            warn.append("%s (ID %d) ไม่ตอบ: เช็คสาย/ไฟเลี้ยง/ID" % (name, sid))
            continue
        ok += 1
        d = _deg(row, f["tick"])
        volts.append(f["volt"])
        flag = ""
        if not (lo - 3 <= d <= hi + 3):
            flag = "  << นอกช่วง %d..%d" % (lo, hi)
        if f["temp"] >= 50:
            warn.append("%s ร้อน %d C" % (name, f["temp"]))
        if f["volt"] < 6.0:
            warn.append("%s ไฟต่ำ %.1f V" % (name, f["volt"]))
        if f["tick"] <= 5 or f["tick"] >= 1018:
            warn.append("%s tick %d ชิดปลายช่วงอ่าน (แกนอาจหลุดช่วง/horn รูด)" % (name, f["tick"]))
        print(" %-11s %3d  %-6s %5d %7.1f %6.1f %5d %6d%s"
              % (name, sid, "ตอบ", f["tick"], d, f["volt"], f["temp"], f["load"], flag))
    print("-" * 66)
    print(" ตอบ %d / %d ตัว" % (ok, len(rows)) + (" ; ไฟ %.1f - %.1f V" % (min(volts), max(volts)) if volts else ""))
    for w in warn:
        print(" !! " + w)
    if scan:
        known = set(r[1] for r in rows)
        found = []
        for sid in range(0, 31):
            if sid in known:
                continue
            try:
                if bus.ping(sid):
                    found.append(sid)
            except Exception:
                pass
        print(" สแกน ID 0..30 ที่ไม่ได้อยู่ใน config: %s" % (found if found else "ไม่มี (ดี)"))
    print("=" * 66)


run()
