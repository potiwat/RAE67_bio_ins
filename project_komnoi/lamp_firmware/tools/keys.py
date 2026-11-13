"""เรียนรู้ลำดับขา keypad 4x3 + ทดสอบกด -- รันบน REPL:  import tools.keys
ไม่สั่งเซอร์โว ไม่ต้องเปิดไฟเซอร์โว

1) กดปุ่มทีละปุ่มตามที่บอก (1 2 3 ... * 0 #) -> ได้ KEY_PAIRS สำหรับ config.py
2) จากนั้นกดอะไรก็ได้ มันจะพิมพ์ชื่อปุ่ม เช็คว่าตรง -> Ctrl-C เพื่อเลิก
"""
import time

import config as cfg
from keypad import Keypad, LAYOUT, make_keypad


def _wait_pair(k, timeout_ms=15000):
    """รอให้กดปุ่มเดียวค้างไว้นิ่ง แล้วรอปล่อย ; คืนคู่ขา หรือ None ถ้าหมดเวลา"""
    t0 = time.ticks_ms()
    same, last = 0, None
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        pr = k.scan_pair()
        if pr is not None and pr == last:
            same += 1
            if same >= 3:
                while k.scan_pair() is not None:      # รอปล่อย
                    time.sleep_ms(20)
                time.sleep_ms(80)
                return pr
        else:
            same, last = 0, pr
        time.sleep_ms(20)
    return None


def learn():
    k = make_keypad(cfg)
    if k is None:
        print("config.KEY_PINS ว่าง -- ยังไม่ได้ตั้งขา keypad")
        return None
    print("กดทีละปุ่มตามที่บอก (กดแล้วปล่อย) ; Ctrl-C เพื่อหยุด")
    pairs, used = {}, {}
    for key in LAYOUT:
        while True:
            print("  กด [%s] ..." % key)
            pr = _wait_pair(k)
            if pr is None:
                print("  ไม่เห็นการกดเลย -- เช็คสาย 7 เส้น")
                return None
            if pr in used:
                print("  คู่ขานี้เป็นของปุ่ม [%s] แล้ว -- กด [%s] ใหม่" % (used[pr], key))
                continue
            pairs[key], used[pr] = pr, key
            print("     ได้ขา %d-%d" % pr)
            break
    from keypad import default_pairs
    if pairs == default_pairs():
        print("\nตรงกับลำดับมาตรฐาน -- ไม่ต้องแก้ config (KEY_PAIRS = None ได้)")
    else:
        print("\nใส่บรรทัดนี้ใน config.py แทน KEY_PAIRS = None แล้วส่งขึ้นบอร์ด:")
        print("KEY_PAIRS = %s" % repr(pairs))
    return pairs


def live(pairs=None):
    k = make_keypad(cfg)
    if k is None:
        return
    if pairs:
        k = Keypad(k.pins, pairs)
    print("\nกดอะไรก็ได้ เช็คว่าชื่อปุ่มตรง ; Ctrl-C เพื่อเลิก")
    try:
        while True:
            key = k.poll(time.ticks_ms())
            if key is not None:
                print("  ปุ่ม", key)
            time.sleep_ms(5)
    except KeyboardInterrupt:
        pass


def run():
    try:
        pairs = learn()
    except KeyboardInterrupt:
        print("\nหยุดการเรียนรู้")
        pairs = None
    live(pairs)


run()
