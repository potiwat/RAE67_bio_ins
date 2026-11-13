"""อัลตร้าโซนิค HC-SR04 -- วัดระยะคน (แทนกล้อง)

ต่อที่ 3.3V (หมุดแดงตอนจัมเปอร์ V-3V3) -> Echo ต่อตรงเข้า ESP32 ได้
ค่าดิบกระโดดบ่อย จึงกรอง 2 ชั้น: median 3 ค่าล่าสุด (ตัดค่าหลุด) -> low-pass (ให้เรียบ)
ตามแนว C2 ของ Lab 02 ; ค่าที่ใช้ไม่ได้ไม่ถูกนับ ถ้าไม่มีค่าดีนานเกิน -> dist = None

    u = make_ultrasonic(cfg)
    u.poll(now_ms)       # เรียกได้ทุกรอบ จะยิงจริงตาม US_PERIOD_MS (บล็อกได้ถึง ~25 ms ตอนยิง)
    u.dist               # เมตร (กรองแล้ว) หรือ None
    u.raw_m              # ค่าล่าสุดก่อนกรอง หรือ None
"""
import time

SOUND_M_PER_US = 0.000343        # 343 m/s ที่ ~20 องศา


class Ultrasonic:
    def __init__(self, trig, echo_pulse, period_ms=60, min_m=0.02, max_m=4.0,
                 alpha=0.4, stale_ms=500, sleep_us=None, ticks_diff=None):
        """trig = Pin ขา Trig ; echo_pulse(timeout_us) -> ความยาวพัลส์ us (ติดลบ = timeout)"""
        self.trig, self.echo_pulse = trig, echo_pulse
        self.period_ms, self.min_m, self.max_m = period_ms, min_m, max_m
        self.alpha, self.stale_ms = alpha, stale_ms
        self.timeout_us = int(2 * max_m / SOUND_M_PER_US) + 2000
        self._sleep_us = sleep_us or time.sleep_us
        self._diff = ticks_diff or time.ticks_diff
        self.raw_m = None
        self.dist = None
        self._recent = []
        self._f = None
        self.last_ms = None
        self.last_good_ms = None
        self.bad = 0
        self.trig.value(0)

    def ping_m(self):
        """ยิงหนึ่งครั้ง คืนระยะ (m) หรือ None ถ้าไม่มีเสียงสะท้อน/นอกช่วง"""
        self.trig.value(0)
        self._sleep_us(2)
        self.trig.value(1)
        self._sleep_us(10)
        self.trig.value(0)
        try:
            us = self.echo_pulse(self.timeout_us)
        except Exception:
            return None
        if us is None or us <= 0:
            return None
        m = us * SOUND_M_PER_US / 2.0
        if not (self.min_m <= m <= self.max_m):
            return None
        return m

    def poll(self, now_ms):
        """ยิงเมื่อครบรอบ ; คืน True ถ้าเพิ่งยิง"""
        if self.last_ms is not None and self._diff(now_ms, self.last_ms) < self.period_ms:
            return False
        self.last_ms = now_ms
        self.raw_m = self.ping_m()
        if self.raw_m is None:
            self.bad += 1
        else:
            self._recent.append(self.raw_m)
            if len(self._recent) > 3:
                self._recent.pop(0)
            med = sorted(self._recent)[len(self._recent) // 2]
            self._f = med if self._f is None else self._f + self.alpha * (med - self._f)
            self.last_good_ms = now_ms
        if self.last_good_ms is None or self._diff(now_ms, self.last_good_ms) > self.stale_ms:
            self.dist = None                     # ไม่มีค่าดีนานเกิน = ไม่รู้ ไม่ใช่ "ไม่มีคน"
            self._recent = []
            self._f = None
        else:
            self.dist = self._f
        return True


class UltrasonicIRQ(Ultrasonic):
    """แบบไม่บล็อก สำหรับลูปหลัก (ลูปเซอร์โว 20 ms รอเสียงสะท้อน 25 ms ไม่ได้)

    ยิง Trig แล้วไปทำงานอื่นต่อ ; interrupt ที่ขา Echo จดเวลาขอบขึ้น/ลงเอง
    poll รอบถัดไปค่อยเก็บผลของการยิงครั้งก่อน -> ค่าช้าไปหนึ่งรอบ (60 ms) ซึ่งไม่มีผลกับโคม
    """

    def __init__(self, trig, echo_pin, ticks_us=None, **kw):
        Ultrasonic.__init__(self, trig, None, **kw)
        self._ticks_us = ticks_us or time.ticks_us
        self._t_rise = None
        self._width = None
        self._armed = False
        P = type(echo_pin)
        echo_pin.irq(handler=self._edge, trigger=P.IRQ_RISING | P.IRQ_FALLING)

    def _edge(self, pin):
        t = self._ticks_us()
        if pin.value():
            self._t_rise = t
        elif self._t_rise is not None:
            self._width = self._diff(t, self._t_rise)
            self._t_rise = None

    def ping_m(self):
        w, armed = self._width, self._armed
        self._width = None
        self._t_rise = None
        self.trig.value(0)
        self._sleep_us(2)
        self.trig.value(1)
        self._sleep_us(10)
        self.trig.value(0)
        self._armed = True
        if not armed or w is None or w <= 0:
            return None
        m = w * SOUND_M_PER_US / 2.0
        return m if self.min_m <= m <= self.max_m else None


def make_ultrasonic(cfg, blocking=True):
    """สร้างจาก config.py ; คืน None ถ้าไม่ได้ต่อ (US_PIN_TRIG = None)"""
    pin_t = getattr(cfg, "US_PIN_TRIG", None)
    if pin_t is None:
        return None
    from machine import Pin, time_pulse_us
    trig = Pin(pin_t, Pin.OUT, value=0)
    echo = Pin(cfg.US_PIN_ECHO, Pin.IN)
    if not blocking:                                     # ลูปหลักของโคม
        return UltrasonicIRQ(trig, echo, period_ms=getattr(cfg, "US_PERIOD_MS", 60),
                             max_m=getattr(cfg, "US_MAX_M", 4.0))
    return Ultrasonic(trig, lambda t: time_pulse_us(echo, 1, t),
                      period_ms=getattr(cfg, "US_PERIOD_MS", 60),
                      max_m=getattr(cfg, "US_MAX_M", 4.0))
