"""แปลงระหว่าง "องศาที่ข้อต่อ" กับ "tick ของเซอร์โว" + เก็บค่าคาลิเบรต

สร้างจากตาราง JOINTS ใน config.py ตอนคาลิเบรตเสร็จให้แก้ center_tick/invert ในนั้น
"""
from config import JOINTS, TICKS_PER_DEG, TICK_MIN, TICK_MAX


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


class Joint:
    def __init__(self, name, sid, center_tick, invert, soft_min, soft_max, max_rate, load_limit):
        self.name, self.sid = name, sid
        self.center_tick, self.invert = center_tick, invert
        self.soft_min, self.soft_max = soft_min, soft_max
        self.max_rate, self.load_limit = max_rate, load_limit

    def deg_to_tick(self, deg, clamp_soft=True):
        """clamp_soft=False ใช้เฉพาะจาก ActuatorSafety ซึ่ง clamp เป้าหมายมาแล้ว
        จำเป็นตอนบูตมาแล้วข้อต่ออยู่นอกช่วง: ต้องค่อยๆ ไล่เข้าช่วง ไม่ใช่กระโดดเข้าทันที"""
        if clamp_soft:
            deg = clamp(deg, self.soft_min, self.soft_max)
        t = self.center_tick + (-deg if self.invert else deg) * TICKS_PER_DEG
        return int(clamp(t, TICK_MIN, TICK_MAX) + 0.5)

    def goal_speed(self):
        """เพดานความเร็วฝั่งเซอร์โวเอง (ticks/s) -- ชั้นกันซ้ำเผื่อซอฟต์แวร์พลาด
        หน่วยของ goal speed ต่างกันไปตามรุ่น ถ้าหุ่นขยับช้า/เร็วผิดปกติให้จูนตัวคูณนี้"""
        v = int(self.max_rate * TICKS_PER_DEG)
        return 1 if v < 1 else (1023 if v > 1023 else v)

    def tick_to_deg(self, tick):
        d = (tick - self.center_tick) / TICKS_PER_DEG
        return -d if self.invert else d

    def tick_range(self):
        """ช่วง tick ที่ soft limit อนุญาต (ไว้เขียนลง EEPROM ของเซอร์โวเป็นชั้นกันซ้ำ)"""
        a, b = self.deg_to_tick(self.soft_min), self.deg_to_tick(self.soft_max)
        return (a, b) if a < b else (b, a)


JOINT_LIST = [Joint(*row) for row in JOINTS]
JOINT_BY_NAME = {j.name: j for j in JOINT_LIST}
NAMES = tuple(j.name for j in JOINT_LIST)
