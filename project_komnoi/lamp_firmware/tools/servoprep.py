"""เตรียมเซอร์โวตัวสำรองก่อนประกอบ (ID 1 = head_roll) -- รันบน REPL:  import tools.servoprep
ต้องเปิดไฟเซอร์โว ; ตัวที่ ID 1 ตัวเก่า (เสีย) ต้องถอดสายออกจากบัสแล้ว

1) อ่านขีดใน EEPROM ; ถ้าไม่เต็มช่วง (0..1023) -> ถามก่อน แล้วปลดล็อก เขียนใหม่ ล็อกกลับ
2) หมุนไปกึ่งกลางกลไก (tick 512 = 150 องศาของช่วง 300 องศา)
3) ค้างแรงบิดไว้ให้ประกอบหัวโดยแกนไม่เลื่อน -> กด Enter เมื่อประกอบเสร็จ แล้วจึงปลดแรงบิด
"""
import time

import config as cfg
from machine import UART, Pin
from scs import (SCSBus, ADDR_MIN_ANGLE, ADDR_MAX_ANGLE, ADDR_MAX_TORQUE,
                 ADDR_GOAL_POSITION, ADDR_GOAL_SPEED)

SID = 1
CENTER = 512
ADDR_LOCK = 48           # SCS (SCSCL): 0 = ปลดล็อก EEPROM, 1 = ล็อก
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


def _limits():
    return bus.read_word(SID, ADDR_MIN_ANGLE), bus.read_word(SID, ADDR_MAX_ANGLE), bus.read_word(SID, ADDR_MAX_TORQUE)


def _open_limits():
    bus.torque(SID, False)
    bus.write(SID, ADDR_LOCK, bytes([0]))
    time.sleep_ms(20)
    bus.write_word(SID, ADDR_MIN_ANGLE, 0)
    time.sleep_ms(20)
    bus.write_word(SID, ADDR_MAX_ANGLE, 1023)
    time.sleep_ms(20)
    bus.write(SID, ADDR_LOCK, bytes([1]))
    time.sleep_ms(50)


def _move_center():
    bus.write_word(SID, ADDR_GOAL_SPEED, 150)
    bus.torque(SID, True)
    bus.write_word(SID, ADDR_GOAL_POSITION, CENTER)
    t0 = time.ticks_ms()
    high_since = None
    f = None
    while time.ticks_diff(time.ticks_ms(), t0) < 4000:
        f = _fb()
        if f is not None:
            if f["temp"] > TEMP_ABORT:
                print("  !! ร้อน %d C" % f["temp"])
                return None
            if abs(f["load"]) > LOAD_ABORT:
                high_since = high_since or time.ticks_ms()
                if time.ticks_diff(time.ticks_ms(), high_since) > 300:
                    print("  !! load %d ค้าง -- ติด" % f["load"])
                    return None
            else:
                high_since = None
            if abs(f["tick"] - CENTER) <= 3:
                break
        time.sleep_ms(50)
    return f


def run():
    print("=" * 56 + "\n เตรียมเซอร์โว ID %d ก่อนประกอบ\n" % SID + "=" * 56)
    if bus.ping(SID) is None:
        print("  ID %d ไม่ตอบ -- เปิดไฟเซอร์โวหรือยัง?" % SID)
        return
    lo, hi, tq = _limits()
    print("[1] EEPROM: ขีดล่าง=%s ขีดบน=%s แรงบิดสูงสุด=%s" % (lo, hi, tq))
    if (lo, hi) != (0, 1023):
        ans = input("    ขีดไม่เต็มช่วง -- เขียนเป็น 0..1023 ไหม? (y/n): ").strip().lower()
        if ans != "y":
            print("    ไม่แก้ -- หยุด")
            return
        _open_limits()
        lo, hi, tq = _limits()
        print("    หลังแก้: ขีดล่าง=%s ขีดบน=%s" % (lo, hi))
        if (lo, hi) != (0, 1023):
            print("    !! เขียนไม่เข้า -- ส่งผลนี้ให้ Claude")
            return
    try:
        print("\n[2] หมุนไปกึ่งกลางกลไก (tick %d) ..." % CENTER)
        f = _move_center()
        if f is None or abs(f["tick"] - CENTER) > 3:
            print("    !! ไปไม่ถึงกลาง (ได้ %s) -- ส่งผลนี้ให้ Claude" % (f["tick"] if f else "?"))
            return
        print("    ถึงแล้ว: tick %d  load %d  temp %d" % (f["tick"], f["load"], f["temp"]))
        print("\n[3] ค้างแรงบิดไว้ -- ประกอบหัวให้ \"ตั้งตรง ไม่เอียง\" ตอนนี้")
        print("    (ใส่ horn ให้หัวตั้งตรง แล้วขันน็อต ; อย่าบิดแกนแรงๆ)")
        input("    ประกอบเสร็จแล้วกด Enter ...")
        f = _fb()
        if f is not None:
            print("    หลังประกอบ: tick %d (ควรยังใกล้ %d)  load %d" % (f["tick"], CENTER, f["load"]))
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    finally:
        try:
            bus.torque(SID, False)
        except Exception:
            pass
        print("  ปลดแรงบิดแล้ว")


run()
