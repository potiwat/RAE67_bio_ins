"""ตรวจบัสก่อนใช้งานจริง -- รันบน REPL ของ ESP32:  import tools.scan

เช็คให้ครบ 4 อย่าง
  1. เจอเซอร์โว ID ไหนบ้าง
  2. endianness ถูกไหม (ถ้าผิด ค่ามุมจะพุ่งเป็นหมื่น)
  3. memory table ตรงกับที่โค้ดคิดไหม (เขียน goal แล้วอ่านกลับ)
  4. สายเสถียรแค่ไหน (อ่าน 200 ครั้ง นับที่พลาด)
"""
from machine import UART, Pin
import time

import config as cfg
from scs import (SCSBus, ADDR_PRESENT_POSITION, ADDR_GOAL_POSITION,
                 ADDR_MAX_ANGLE, ADDR_PRESENT_TEMPERATURE)


def make_bus(big_endian=None):
    dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
    uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
    be = cfg.SCS_BIG_ENDIAN if big_endian is None else big_endian
    return SCSBus(uart, dir_pin=dir_pin, big_endian=be, baud=cfg.BAUD)


def scan(max_id=20):
    bus = make_bus()
    found = []
    for sid in range(1, max_id + 1):
        if bus.ping(sid) is not None:
            found.append(sid)
    print("เจอ ID:", found)
    if not found:
        print("ไม่เจอเลย -> เช็ค: ไฟเลี้ยงเซอร์โว, สาย TX/RX/DIR, baud (ลอง 115200), กราวด์ร่วม")
    return found


def check_endian(sid):
    """ดูที่ max angle limit (ปกติ 1023 = 0x03FF) เพราะสลับไบต์แล้วค่าจะเพี้ยนชัด
    ส่วน present position เชื่อไม่ได้ ถ้าบังเอิญอยู่ที่ 512 (0x0200) สลับแล้วได้ 2 ซึ่งดูสมเหตุสมผล"""
    for be in (True, False):
        b = make_bus(be)
        mx = b.read_word(sid, ADDR_MAX_ANGLE)
        pos = b.read_word(sid, ADDR_PRESENT_POSITION)
        tag = "big" if be else "little"
        ok = mx is not None and 0 <= mx <= 1100 and pos is not None and 0 <= pos <= 1100
        print("%-7s endian -> max_angle = %s, position = %s  %s"
              % (tag, mx, pos, "OK" if ok else "ผิด"))
    print("เอาอันที่ OK ไปตั้ง SCS_BIG_ENDIAN ใน config.py")
    print("ถ้า OK ทั้งคู่ ให้หมุนข้อต่อด้วยมือไปสุดฝั่งหนึ่งแล้วรันใหม่ (ค่าจะห่างจาก 512 มากขึ้น)")


def check_table(sid):
    """เขียน goal position เท่ากับมุมปัจจุบัน แล้วอ่านกลับ -- ไม่ทำให้ข้อต่อขยับ"""
    b = make_bus()
    pos = b.read_word(sid, ADDR_PRESENT_POSITION)
    if pos is None:
        print("อ่าน position ไม่ได้")
        return
    b.write_word(sid, ADDR_GOAL_POSITION, pos)
    back = b.read_word(sid, ADDR_GOAL_POSITION)
    print("present=%s  เขียน goal=%s  อ่าน goal กลับ=%s  %s"
          % (pos, pos, back, "ตรง" if back == pos else "ไม่ตรง -> memory table ไม่ใช่ตัวนี้"))
    fb = b.feedback(sid)
    print("feedback:", fb)
    if fb and not (0 <= fb["temp"] <= 100 and 4.0 <= fb["volt"] <= 13.0):
        print("temp/volt ดูไม่สมเหตุสมผล -> addr 56..63 อาจไม่ตรงรุ่น")


def stress(sid, n=200):
    b = make_bus()
    t0 = time.ticks_ms()
    for _ in range(n):
        b.feedback(sid)
    ms = time.ticks_diff(time.ticks_ms(), t0)
    print("อ่าน %d ครั้ง: สำเร็จ %d พลาด %d ใช้เวลา %d ms (%.2f ms/ครั้ง)"
          % (n, b.ok, b.errors, ms, ms / n))
    if b.errors:
        print("มีพลาด -> ลดความยาวสาย, เช็คกราวด์, หรือลด BAUD เป็น 500000/115200")


def run(sid=None):
    found = scan()
    if not found:
        return
    sid = sid or found[0]
    print("\n--- endianness (ID %d) ---" % sid)
    check_endian(sid)
    print("\n--- memory table (ID %d) ---" % sid)
    check_table(sid)
    print("\n--- ความเสถียรของสาย (ID %d) ---" % sid)
    stress(sid)


run()
