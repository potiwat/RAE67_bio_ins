"""สแกนบัสละเอียด: ทุก baud ที่ใช้บ่อย x ทุก ID (0..253) -- รันบน REPL:  import tools.scanall
ใช้หาเซอร์โวที่ "ไม่เจอ" ตอนสแกนปกติ (baud ไม่ตรง หรือ ID แปลก) ; ไม่สั่งขยับอะไร ; ใช้เวลา ~20 วินาที
หลังรันเสร็จ บัสกลับไปที่ baud ของโคม (config.BAUD) แต่ควรกด Ctrl-D รีเซ็ตก่อนรันอย่างอื่นต่อ
"""
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus

BAUDS = (1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None


def _bus(baud):
    u = UART(cfg.UART_ID, baudrate=baud, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
    return SCSBus(u, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=baud,
                  timeout_ms=6 if baud >= 500000 else 12)


def run():
    known = set(j[1] for j in cfg.JOINTS)
    print("=" * 56 + "\n สแกนละเอียด (ข้อต่อโคม = %s)\n" % sorted(known) + "=" * 56)
    hits = []
    try:
        for baud in BAUDS:
            b = _bus(baud)
            found = []
            for sid in range(0, 254):
                try:
                    if b.ping(sid) is not None:
                        found.append(sid)
                except Exception:
                    pass
            new = [s for s in found if not (baud == cfg.BAUD and s in known)]
            print("  baud %7d : %s%s" % (baud, found if found else "-",
                                         "   << ตัวใหม่: %s" % new if new else ""))
            for s in new:
                hits.append((baud, s))
            time.sleep_ms(20)
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    _bus(cfg.BAUD)
    print()
    if hits:
        for baud, s in hits:
            print(" เจอ: ID %d ที่ baud %d" % (s, baud))
        print(" ส่งบรรทัดนี้ให้ Claude -> จะตั้ง ID/baud ให้ตรงกับโคม")
    else:
        print(" ไม่เจอตัวใหม่เลยทุก baud -- น่าจะเป็นเรื่องสาย/ไฟ: เช็คหัวเสียบ ทิศสาย และไฟเลี้ยงถึงตัวสำรอง")


run()
