"""ไฟของโคม: PWM ขาเดียว (ขาวหรี่-สว่าง) หรือ NeoPixel (เปลี่ยนสีได้)
ถ้าไม่มีไฟต่ออยู่ ทุกอย่างยังทำงานปกติ แค่ไม่มีอะไรสว่าง
"""
import math

COOL = (205, 225, 255)          # (เก็บไว้ให้ tools.all / tools.ring ใช้ทดสอบไฟ)
WARM = (255, 185, 100)
MAX_DUTY = 0.95          # เพดานความสว่าง (กันแยงตาคน)

# สีตามอารมณ์ = ตาราง RGB ของ Lab 06 (normal / interested / happy / afraid / sleepy)
EMOTION_RGB = {
    "Idle": (60, 90, 140),        # normal: ฟ้าเทา
    "Curious": (255, 180, 0),     # interested: อำพัน
    "Engage": (40, 220, 80),      # happy: เขียว
    "Fear": (230, 30, 30),         # afraid: แดง
    "Sleep": (50, 40, 100),       # sleepy: ม่วงหรี่
    "Peek": (50, 40, 100),        # หลับแล้วแอบดู: ยังม่วงเหมือนหลับ
    "Sick": (150, 165, 90),       # ป่วย: เขียวมะกอกซีด (= SICK_RGB)
}
SICK_RGB = (150, 165, 90)       # ป่วย: เหลืองเขียวซีด (แล็บไม่มี -- เพิ่มเอง)
SICK_PULSE, SICK_PULSE_HZ = 0.5, 0.35   # ป่วยหนักสุด ไฟหรี่ลงได้ครึ่งหนึ่งเป็นจังหวะช้าๆ
FAULT_RGB = (200, 200, 200)
# ไฟวิ่งวนตอนมองตาม: รอบ/วินาที (จ้องนิ่ง -> หมุนหันเต็มที่), หางยาวกี่เม็ด, เม็ดพื้นสว่างเท่าไรของหัว
CHASE_SLOW, CHASE_FAST, CHASE_TAIL, CHASE_BASE = 0.4, 1.5, 5.0, 0.15     # Blind/Protect: ขาวหรี่กะพริบช้า (ไม่ใช้ส้ม เพราะชนกับอำพันของ Curious)


class Light:
    """สี = อารมณ์ (EMOTION_RGB) ; ความสว่าง = พารามิเตอร์ brightness จากฮอร์โมน
    พารามิเตอร์ warmth ใช้เป็น "ความแข็งแรง": 1 = ปกติ, 0 = ป่วยหนัก -> สีซีดไปทาง SICK_RGB
    (ใช้ช่องเดิมของโปรโตคอล ไม่ต้องแก้ link.py) ; เปลี่ยนอารมณ์แล้วสีค่อยๆ เฟด"""

    def __init__(self, pwm=None, neopixel=None, n=1, max_b=MAX_DUTY):
        self.pwm, self.np, self.n = pwm, neopixel, n
        self.max_b = min(max_b, MAX_DUTY)
        self.b, self.w = 0.0, 1.0
        self.rgb = [60.0, 90.0, 140.0]
        self._last_px = None            # สีที่เขียนล่าสุด -> ไม่เปลี่ยนก็ไม่ต้องเขียนซ้ำ (เขียนวงแหวนกินเวลาลูป)
        self._chase = 0.0               # ตำแหน่งหัวขบวนไฟวิ่ง (เม็ด)

    def update(self, brightness, warmth, mode, now, dt, track=0.0):
        """track = 0 ไม่ได้มองตาม ; >0 กำลังมองตาม (ไฟวิ่งวน) ; ค่ามาก = กำลังหมุนหันเร็ว ; เครื่องหมาย = ทิศ"""
        k = 1.0 - math.exp(-dt / 0.25)                 # เปลี่ยนแบบค่อยเป็นค่อยไป
        self.b += (min(max(brightness, 0.0), 1.0) - self.b) * k
        self.w += (min(max(warmth, 0.0), 1.0) - self.w) * k
        fault = mode not in EMOTION_RGB
        target = FAULT_RGB if fault else EMOTION_RGB[mode]
        if not fault:
            sick = 1.0 - self.w                         # ป่วยหนักสุด ซีดเต็มที่ (ผู้ใช้: ให้เห็นชัด)
            target = [c + (s - c) * sick for c, s in zip(target, SICK_RGB)]
        kc = 1.0 - math.exp(-dt / 0.35)                # สีเฟดช้ากว่าความสว่างนิดหน่อย
        for i in range(3):
            self.rgb[i] += (target[i] - self.rgb[i]) * kc
        rgb = (int(self.rgb[0]), int(self.rgb[1]), int(self.rgb[2]))
        if fault:                                      # เต้นช้าๆ บอกว่ามีปัญหา (ไม่ใช่กะพริบรัว)
            b = (0.05 + 0.15 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.5 * now))) * self.max_b / MAX_DUTY
        else:
            b = self.b * self.max_b / MAX_DUTY          # สเกลให้ช่วงเต็มของฮอร์โมนอยู่ใต้เพดาน
            sick = 1.0 - self.w
            if sick > 0.1:                              # ป่วย: ไฟหายใจอ่อนแรง (สว่างขึ้นลงช้าๆ)
                b *= 1.0 - SICK_PULSE * sick * (0.5 + 0.5 * math.sin(2 * math.pi * SICK_PULSE_HZ * now))
        if track and not fault and self.np is not None and self.n >= 4:
            # มองตามอยู่ = ไฟสีอารมณ์วิ่งวน ; จ้องนิ่งวิ่งช้า หมุนหัน/หาวิ่งเร็ว ไปทางเดียวกับที่หัน
            speed = CHASE_SLOW + (CHASE_FAST - CHASE_SLOW) * min(1.0, abs(track))
            self._chase += (1.0 if track >= 0 else -1.0) * speed * self.n * dt
            self._write_chase(rgb, b)
            return rgb, b
        self._write(rgb, b)
        return rgb, b

    def _write_chase(self, rgb, b):
        b = min(max(b, 0.0), self.max_b)
        if self.pwm is not None:
            try:
                self.pwm.duty_u16(int(min(b, MAX_DUTY) * 65535))
            except Exception:
                pass
        n = self.n
        head = self._chase % n
        try:
            for i in range(n):
                k = (head - i) % n                      # ระยะหลังหัวขบวน (0 = หัว)
                f = CHASE_BASE + (1.0 - CHASE_BASE) * max(0.0, 1.0 - k / CHASE_TAIL)
                s = b * f
                self.np[i] = (int(rgb[0] * s), int(rgb[1] * s), int(rgb[2] * s))
            self.np.write()
            self._last_px = None                        # ออกจากโหมดวิ่งแล้วต้องเขียนสีเต็มใหม่
        except Exception:
            pass

    def _write(self, rgb, b):
        b = min(max(b, 0.0), self.max_b)
        if self.pwm is not None:
            try:
                self.pwm.duty_u16(int(min(b, MAX_DUTY) * 65535))
            except Exception:
                pass
        if self.np is not None:
            px = (int(rgb[0] * b), int(rgb[1] * b), int(rgb[2] * b))   # คิดครั้งเดียว ทุกเม็ดสีเดียวกัน
            if px == self._last_px:
                return
            self._last_px = px
            try:
                if hasattr(self.np, "fill"):
                    self.np.fill(px)
                else:
                    for i in range(self.n):
                        self.np[i] = px
                self.np.write()
            except Exception:
                pass
