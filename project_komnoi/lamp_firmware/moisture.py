"""เซนเซอร์ความชื้นดิน (แผ่นแดง แบบวัดความต้านทาน) ใช้เป็น "จุ่มน้ำ = ป่วย"

เปิดไฟเลี้ยงเซนเซอร์เฉพาะตอนอ่าน (ผ่านขา GPIO) เพราะถ้าจ่ายไฟค้างไว้ ขั้วจะกร่อนเร็วมาก
อ่านหลายครั้งแล้วเฉลี่ย -> แปลงเป็น wet 0..1 ด้วยค่า dry/wet ที่วัดจริง (tools/sense.py)

    m = make_moisture(cfg)       # บนบอร์ด
    m.poll(now_ms)               # เรียกได้ทุกรอบ จะอ่านจริงตาม MOIST_PERIOD_MS
    m.wet                        # 0..1 หรือ None ถ้าอ่านไม่ได้
"""
import time


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class Moisture:
    def __init__(self, adc, power, dry_raw, wet_raw, period_ms=1000, settle_ms=10,
                 samples=8, sleep_ms=None, ticks_diff=None):
        assert dry_raw != wet_raw, "dry_raw กับ wet_raw ต้องต่างกัน -- คาลิเบรตด้วย tools/sense.py"
        self.adc, self.power = adc, power
        self.dry_raw, self.wet_raw = dry_raw, wet_raw
        self.period_ms, self.settle_ms, self.samples = period_ms, settle_ms, samples
        self._sleep = sleep_ms or time.sleep_ms
        self._diff = ticks_diff or time.ticks_diff
        self.raw = None
        self.wet = None
        self.last_ms = None
        self.errors = 0
        if self.power is not None:
            self.power.value(0)

    def read_raw(self):
        """เปิดไฟ -> รอนิ่ง -> อ่านเฉลี่ย -> ปิดไฟ ; คืน None ถ้าอ่านพลาด"""
        try:
            if self.power is not None:
                self.power.value(1)
                self._sleep(self.settle_ms)
            total = 0
            for _ in range(self.samples):
                total += self.adc.read_u16()      # 0..65535 ทุกพอร์ต
            return total // self.samples
        except Exception:
            self.errors += 1
            return None
        finally:
            if self.power is not None:
                self.power.value(0)

    def to_wet(self, raw):
        """raw -> 0..1 รองรับทั้งแบบที่จุ่มน้ำแล้วค่าลดหรือค่าเพิ่ม"""
        if raw is None:
            return None
        return _clamp((raw - self.dry_raw) / (self.wet_raw - self.dry_raw), 0.0, 1.0)

    def poll(self, now_ms):
        """อ่านจริงเมื่อครบรอบ ; คืน True ถ้าเพิ่งอ่านค่าใหม่"""
        if self.last_ms is not None and self._diff(now_ms, self.last_ms) < self.period_ms:
            return False
        self.last_ms = now_ms
        self.raw = self.read_raw()
        self.wet = self.to_wet(self.raw)
        return True


def make_moisture(cfg):
    """สร้างจากค่าใน config.py ; คืน None ถ้าไม่ได้ต่อเซนเซอร์ (MOIST_PIN_AO = None)"""
    pin_ao = getattr(cfg, "MOIST_PIN_AO", None)
    if pin_ao is None:
        return None
    from machine import ADC, Pin
    try:
        adc = ADC(Pin(pin_ao), atten=ADC.ATTN_11DB)   # อ่านได้เต็มช่วง 0..3.3V
    except TypeError:
        adc = ADC(Pin(pin_ao))
        adc.atten(ADC.ATTN_11DB)
    pin_pwr = getattr(cfg, "MOIST_PIN_PWR", None)
    power = Pin(pin_pwr, Pin.OUT, value=0) if pin_pwr is not None else None
    return Moisture(adc, power, cfg.MOIST_DRY_RAW, cfg.MOIST_WET_RAW,
                    period_ms=getattr(cfg, "MOIST_PERIOD_MS", 1000))
