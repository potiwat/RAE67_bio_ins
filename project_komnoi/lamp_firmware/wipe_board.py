"""ล้างไฟล์เก่าบนบอร์ด (เก็บ boot.py ไว้) -- รันจากคอม:
    mpremote connect COM5 run wipe_board.py
ไฟล์นี้ไม่ต้องส่งขึ้นบอร์ด
"""
import os

KEEP = ("boot.py",)


def _is_dir(path):
    return os.stat(path)[0] & 0x4000


def _wipe(path=None):
    names = os.listdir() if path is None else os.listdir(path)
    for name in names:
        full = name if path is None else path + "/" + name
        if path is None and name in KEEP:
            continue
        if _is_dir(full):
            _wipe(full)
            os.rmdir(full)
            print("ลบโฟลเดอร์", full)
        else:
            os.remove(full)
            print("ลบ", full)


_wipe()
os.mkdir("tools")
print("เหลือ:", os.listdir())
print("ล้างเสร็จ -- ส่งไฟล์ชุดใหม่ขึ้นได้เลย")
