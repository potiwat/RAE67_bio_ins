"""รวมเซนเซอร์ทั้งหมดของโคม ไว้ใช้ในลูปหลัก -> ส่งขึ้นโน้ตบุ๊กพร้อม telemetry

อะไรไม่ได้ต่อ/พัง ก็ข้ามไป ส่งค่า "ไม่รู้" แทน (ไม่ใช่ค่าศูนย์ปลอมๆ)
ทุกตัวไม่บล็อกลูปเซอร์โว: อัลตร้าโซนิคใช้ interrupt, ความชื้นอ่านวินาทีละครั้ง (~10 ms), keypad <1 ms
"""
NO_DIST = 0xFFFF
NO_WET = 255


class Sensors:
    def __init__(self, ultrasonic=None, moisture=None, keypad=None, log=None):
        self.u, self.m, self.k = ultrasonic, moisture, keypad
        self.log = log or (lambda s: None)
        self.key = None           # ปุ่มล่าสุดที่กด
        self.key_seq = 0          # นับจำนวนครั้งที่กด (วน 0..255) -> โน้ตบุ๊กรู้ว่ามีกดใหม่ แม้ปุ่มเดิม
        self.err = 0

    def poll(self, now_ms):
        for name, dev in (("ultrasonic", self.u), ("moisture", self.m)):
            if dev is None:
                continue
            try:
                dev.poll(now_ms)
            except Exception as e:
                self._fail(name, e)
        if self.k is not None:
            try:
                key = self.k.poll(now_ms)
                if key is not None and key != "?":
                    self.key = key
                    self.key_seq = (self.key_seq + 1) & 0xFF
            except Exception as e:
                self._fail("keypad", e)

    def _fail(self, name, e):
        self.err += 1
        if self.err <= 3:
            self.log("sensor %s พัง: %s" % (name, e))

    def fields(self):
        """(dist_mm, wet_pct, key_code, key_seq) สำหรับ link.encode_telemetry"""
        d = self.u.dist if self.u is not None else None
        w = self.m.wet if self.m is not None else None
        return (NO_DIST if d is None else min(int(d * 1000), NO_DIST - 1),
                NO_WET if w is None else int(round(w * 100)),
                0 if self.key is None else ord(self.key),
                self.key_seq)


def make_sensors(cfg, log=None):
    from moisture import make_moisture
    from ultrasonic import make_ultrasonic
    from keypad import make_keypad
    made = {}
    for name, fn in (("u", lambda: make_ultrasonic(cfg, blocking=False)),
                     ("m", lambda: make_moisture(cfg)),
                     ("k", lambda: make_keypad(cfg))):
        try:
            made[name] = fn()
        except Exception as e:
            made[name] = None
            if log:
                log("sensor %s ใช้ไม่ได้: %s" % (name, e))
    return Sensors(made["u"], made["m"], made["k"], log=log)
