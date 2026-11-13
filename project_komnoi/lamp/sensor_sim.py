"""สถานการณ์จำลองของเซนเซอร์ (ไม่ต้องมีบอร์ด) -- ให้ telemetry หน้าตาเหมือนของจริง

เวลา (วินาที)   เหตุการณ์
  0 -   8      ไม่มีใคร (เห็นผนัง 2.6 m)
  8 -  14      คนเดินเข้ามาช้าๆ 1.2 -> 0.45 m (ระยะตรวจจับ 0.7 m ; สนใจหลังอยู่ในระยะ 3 วิ)
 14 -  62      ยืนที่ 0.45 m (โยกตัวเบาๆ) ; ลูบหัว (1) ที่ 16-28 ทุก 2 วิ -> ผูกพัน
 32            ตบหัว (7)
 41 -  53      จุ่มเซนเซอร์ลงน้ำ (ป่วย) ทั้งที่คนยังยืนอยู่
 53            ยกขึ้น ; ลูบหัว (1) ที่ 54, 56, 58 (ดูแล)
 62            พุ่งเข้ามาเร็ว 0.65 -> 0.12 m ใน 0.35 วิ
 64            เดินออกไป
 66 - 101      ไม่มีใคร -> ง่วง/หลับ
 101           กดปลุก (5)
 วนซ้ำทุก 110 วินาที
"""
import math

WALL_M = 2.6
SWAY_M = 0.04          # คนจริงยืนไม่นิ่ง โยกตัวไปมา ~+-4 ซม. (ไม่งั้น habituation จะนับเป็นฉากหลัง)
PERIOD_S = 110.0
KEYS = ((16, "1"), (18, "1"), (20, "1"), (22, "1"), (24, "1"), (26, "1"), (28, "1"), (32, "7"),
        (54, "1"), (56, "1"), (58, "1"), (101, "5"))


def _lerp(a, b, t):
    return a + (b - a) * min(max(t, 0.0), 1.0)


def scripted_reading(t):
    """t = วินาทีตั้งแต่เริ่ม -> (dist_m, wet, จำนวนปุ่มที่กดไปแล้วในรอบนี้, ปุ่มล่าสุด)"""
    t = t % PERIOD_S
    if t < 8:
        d = WALL_M
    elif t < 14:
        d = _lerp(1.2, 0.45, (t - 8) / 6)
    elif t < 62:
        d = 0.45 + SWAY_M * math.sin(2 * math.pi * 0.35 * t)
    elif t < 62.35:
        d = _lerp(0.65, 0.12, (t - 62) / 0.35)
    elif t < 64:
        d = 0.12
    elif t < 66:
        d = _lerp(0.12, WALL_M, (t - 64) / 2)
    else:
        d = WALL_M
    wet = 1.0 if 41 <= t < 53 else 0.0
    n, last = 0, None
    for kt, k in KEYS:
        if t >= kt:
            n, last = n + 1, k
    return d, wet, n, last


class ScriptedSensors:
    def __init__(self, t0, speed=1.0):
        self.t0, self.speed = t0, speed
        self._cycle_keys = 0

    def read(self, now):
        t = (now - self.t0) * self.speed
        d, wet, n, last = scripted_reading(t)
        cycle = int(t // PERIOD_S)
        seq = (cycle * len(KEYS) + n) & 0xFF
        return {"dist_m": round(d, 3), "wet": wet, "key": last, "key_seq": seq, "t_rx": now,
                "state": "-", "fault": 0, "seq": 0, "t_ms": 0, "joints": []}
