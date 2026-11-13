"""ทดสอบเซอร์โวตัวสำรองบนโต๊ะ (ยังไม่ประกอบเข้าหุ่น) -- รันบน REPL:  import tools.servotest
ต้องเปิดไฟเซอร์โว ; ถอดตัวที่ ID ซ้ำออกจากบัสก่อน

1) สแกนหา ID ที่ตอบแต่ไม่ใช่ข้อต่อของโคม (ตัวสำรอง) ; ถ้ามีหลายตัวจะถามว่าใช้ตัวไหน
2) แกว่ง +-75 tick (~22 องศา) รอบตำแหน่งปัจจุบัน 3 รอบ ให้เห็นว่าหมุนจริงไหม
ติดจริง (load > 500 ค้าง 0.3 วิ + ไม่ขยับ) หรือร้อนเกิน 45C -> ปลดแรงบิด ; จบแล้วปลดแรงบิดเสมอ
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus, ADDR_GOAL_POSITION, ADDR_GOAL_SPEED

SWING = 75
LOAD_ABORT = 500
_results = []            # ไปถึงเป้าไหม ทุกครั้งที่สั่ง
TEMP_ABORT = 45

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


def _go(sid, goal, label, wait_ms=1500):
    bus.write_word(sid, ADDR_GOAL_POSITION, goal)
    t0 = time.ticks_ms()
    f = None
    path = []
    high_since, tick_at_high = None, None
    while time.ticks_diff(time.ticks_ms(), t0) < wait_ms:
        f = _fb(sid)
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
                    print("  !! %s: ติด -- load %d ค้าง tick ไม่ขยับ (%d) -- ปลดแรงบิด"
                          % (label, f["load"], f["tick"]))
                    print("     ทาง: %s" % path[::3])
                    return False
            else:
                high_since = None
        time.sleep_ms(50)
    if f is None:
        print("  %s: อ่านค่าไม่ได้" % label)
        return False
    ok = abs(f["tick"] - goal) <= 6
    _results.append(ok)
    print("  %-8s สั่ง %4d -> ได้ %4d  load %4d  temp %d  %s   ทาง: %s"
          % (label, goal, f["tick"], f["load"], f["temp"], "ok" if ok else "<< ไปไม่ถึง", path[::4]))
    return True


def find_spares():
    used = set(j[1] for j in cfg.JOINTS)
    found = [s for s in range(0, 31) if bus.ping(s) is not None]
    return found, [s for s in found if s not in used]


def run(sid=None):
    print("=" * 56 + "\n ทดสอบเซอร์โวตัวสำรอง\n" + "=" * 56)
    found, spares = find_spares()
    print("  ID ที่ตอบ: %s   ตัวที่ไม่ใช่ข้อต่อโคม: %s" % (found, spares))
    if sid is None:
        if not spares:
            print("  ไม่เจอตัวสำรอง -- เช็คสาย/ไฟ หรือ ID ของมันซ้ำกับข้อต่อของโคม")
            return
        sid = spares[0]
        if len(spares) > 1:
            ans = input("  เจอหลายตัว %s -- พิมพ์ ID ที่จะทดสอบ: " % spares).strip()
            sid = int(ans) if ans.isdigit() else spares[0]
    f = _fb(sid)
    if f is None:
        print("  ID %d อ่านค่าไม่ได้" % sid)
        return
    mid = min(max(f["tick"], 200), 820)
    print("  ทดสอบ ID %d  เริ่มที่ tick %d  volt %s  temp %d" % (sid, f["tick"], f.get("volt", "?"), f["temp"]))
    try:
        bus.write_word(sid, ADDR_GOAL_SPEED, 150)
        bus.torque(sid, True)
        if not _go(sid, mid, "เริ่ม", 2500):
            return
        for i in range(3):
            if not _go(sid, mid + SWING, "+%d" % (i + 1)):
                return
            if not _go(sid, mid - SWING, "-%d" % (i + 1)):
                return
        _go(sid, mid, "กลับ")
        if _results and all(_results):
            print("\n  ผ่าน: ID %d หมุนได้ปกติ ไปถึงเป้าครบทุกครั้ง" % sid)
        else:
            print("\n  ไม่ผ่าน: ไปไม่ถึงเป้า %d จาก %d ครั้ง -- ถ้าค้างที่ค่าเดิม load 0 = ขีดใน EEPROM แคบ (ใช้ tools.servoprep)"
                  % (_results.count(False), len(_results)))
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    finally:
        try:
            bus.torque(sid, False)
        except Exception:
            pass
        print("  ปลดแรงบิดแล้ว")


run()
