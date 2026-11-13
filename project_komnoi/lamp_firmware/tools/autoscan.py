"""ไล่ลองทุกแบบจนกว่าจะเจอเซอร์โว -- รันบนบอร์ด:  import tools.autoscan

ลองครบทุกคู่ของ
  - baud: 1000000, 500000, 250000, 115200, 57600, 38400
  - การสลับขา TX/RX (ทำในซอฟต์แวร์ ไม่ต้องถอดสาย)
  - endianness ทั้ง big และ little

เจอแล้วจะบอกว่าต้องตั้งอะไรใน config.py
"""
from machine import UART, Pin
import time

import config as cfg
from scs import SCSBus, ADDR_PRESENT_POSITION

BAUDS = (1000000, 500000, 250000, 115200, 57600, 38400)
MAX_ID = 10


def try_combo(tx, rx, baud, big_endian):
    uart = UART(cfg.UART_ID, baudrate=baud, tx=tx, rx=rx, timeout=5)
    time.sleep_ms(50)
    dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
    bus = SCSBus(uart, dir_pin=dir_pin, big_endian=big_endian, baud=baud)
    found = []
    for sid in range(1, MAX_ID + 1):
        if bus.ping(sid) is not None:
            found.append(sid)
    uart.deinit()
    return found, bus


def run():
    print("เริ่มไล่ลอง (ใช้เวลาสัก 1-2 นาที)...\n")
    hits = []
    for tx, rx, label in ((cfg.PIN_TX, cfg.PIN_RX, "ตามที่ตั้งไว้"),
                          (cfg.PIN_RX, cfg.PIN_TX, "สลับ TX/RX")):
        for baud in BAUDS:
            found, bus = try_combo(tx, rx, baud, True)
            if found:
                print(">>> เจอ! tx=%d rx=%d baud=%d -> ID %s" % (tx, rx, baud, found))
                hits.append((tx, rx, baud, found))
            else:
                print("    tx=%d rx=%d baud=%-8d (%s) ไม่เจอ" % (tx, rx, baud, label))

    if not hits:
        print("\nไม่เจอเลยทุกแบบ -> ปัญหาน่าจะอยู่ที่ฮาร์ดแวร์")
        print("  1. ไฟเลี้ยงเซอร์โวเปิดอยู่ไหม (ลองหมุนแขนด้วยมือ ต้องมีแรงต้าน)")
        print("  2. จัมเปอร์เหลืองบน adapter อยู่ฝั่ง A (UART) ไหม")
        print("  3. GND ของ adapter ต่อถึง GND ของ ESP32 ไหม")
        print("  4. สาย TX/RX เสียบที่ขา S ของ G16/G17 ไม่ใช่ขา V")
        print("  5. ลองถอด USB-C ออกจาก adapter ถ้าเสียบอยู่ (ใช้พร้อม UART ไม่ได้)")
        return

    tx, rx, baud, found = hits[0]
    print("\n================ สรุป ================")
    print("เจอ ID: %s" % found)
    print("\nตั้งใน config.py แบบนี้")
    print("  PIN_TX = %d" % tx)
    print("  PIN_RX = %d" % rx)
    print("  BAUD = %d" % baud)

    for be in (True, False):
        uart = UART(cfg.UART_ID, baudrate=baud, tx=tx, rx=rx, timeout=5)
        time.sleep_ms(50)
        dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
        bus = SCSBus(uart, dir_pin=dir_pin, big_endian=be, baud=baud)
        pos = bus.read_word(found[0], ADDR_PRESENT_POSITION)
        ok = pos is not None and 0 <= pos <= 1100
        print("  SCS_BIG_ENDIAN = %-5s -> position = %s %s"
              % (be, pos, "<- ใช้อันนี้" if ok else ""))
        uart.deinit()

    if len(found) < 5:
        print("\nเจอแค่ %d ตัว จาก 5 -> เช็คว่าตั้ง ID ครบ 1-5 และไม่ซ้ำกัน" % len(found))


run()
