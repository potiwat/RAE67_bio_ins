"""Keypad 4x3 (1-9 * 0 #) แทนการสัมผัส -- 7 สาย ต่อลำดับไหนก็ได้

สแกนแบบ "คู่ขา": ดึงขาหนึ่งลง LOW ทีละขา ที่เหลือเป็นอินพุต pull-up
ขาไหนอ่านได้ LOW = ปุ่มที่เชื่อมสองขานั้นถูกกด -> ไม่ต้องรู้ว่าขาไหนเป็นแถว/คอลัมน์
ลำดับขาของแต่ละยี่ห้อต่างกัน จึงเรียนรู้ด้วย tools/keys.py แล้วเก็บใน config.KEY_PAIRS

    k = make_keypad(cfg)
    k.poll(now_ms)   # คืนตัวอักษรปุ่มตอน "เพิ่งกด" (กันเด้งแล้ว) หรือ None
    k.held           # ปุ่มที่กดค้างอยู่ตอนนี้ หรือ None
"""
LAYOUT = "123456789*0#"


def default_pairs():
    """เมมเบรนส่วนใหญ่: ขา 1-4 = แถว 1-4, ขา 5-7 = คอลัมน์ 1-3"""
    return {LAYOUT[r * 3 + c]: (r, 4 + c) for r in range(4) for c in range(3)}


class Keypad:
    def __init__(self, pins, pairs=None, period_ms=20, debounce_n=3, ticks_diff=None):
        """pins = Pin ทั้ง 7 (ต้องมี .init(mode, pull) / .value()) ; pairs = {ปุ่ม: (i, j)}"""
        import time
        self.pins = pins
        self._P = type(pins[0])               # คลาส Pin (เอาค่าคงที่ IN/OUT/PULL_UP)
        self.pairs = pairs or default_pairs()
        self._lookup = {}
        for key, (a, b) in self.pairs.items():
            self._lookup[(min(a, b), max(a, b))] = key
        self.period_ms, self.debounce_n = period_ms, debounce_n
        self._diff = ticks_diff or time.ticks_diff
        self.last_ms = None
        self.held = None
        self._cand, self._count = None, 0
        for p in self.pins:
            self._float(p)

    def _float(self, p):
        p.init(self._P.IN, self._P.PULL_UP)

    def scan_pair(self):
        """คืนคู่ขา (i, j) ที่เชื่อมกันอยู่ หรือ None ; ถ้ากดหลายปุ่มคืนคู่แรกที่เจอ"""
        n = len(self.pins)
        for i in range(n - 1):
            p = self.pins[i]
            p.init(self._P.OUT, value=0)
            hit = None
            for j in range(i + 1, n):
                if self.pins[j].value() == 0:
                    hit = (i, j)
                    break
            self._float(p)
            if hit is not None:
                return hit
        return None

    def scan(self):
        pair = self.scan_pair()
        return None if pair is None else self._lookup.get(pair, "?")

    def poll(self, now_ms):
        """สแกนตามรอบ + กันเด้ง (ต้องเห็นซ้ำ debounce_n ครั้ง) ; คืนปุ่มตอนเพิ่งกด"""
        if self.last_ms is not None and self._diff(now_ms, self.last_ms) < self.period_ms:
            return None
        self.last_ms = now_ms
        k = self.scan()
        if k == self._cand:
            self._count += 1
        else:
            self._cand, self._count = k, 1
        if self._count < self.debounce_n or k == self.held:
            return None
        self.held = k
        return k                      # None = เพิ่งปล่อย (ไม่ส่งเป็นเหตุการณ์)


def make_keypad(cfg):
    pins = getattr(cfg, "KEY_PINS", None)
    if not pins:
        return None
    from machine import Pin
    return Keypad([Pin(n, Pin.IN, Pin.PULL_UP) for n in pins], getattr(cfg, "KEY_PAIRS", None))
