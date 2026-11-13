"""Artificial Hormone Mechanism (AHM) ตามหัวข้อ 5 และ 7 ของ design notes

    H <- clamp( H + alpha*S*(1 - H) - beta*H - gamma*H , 0, 1 )

โคมมี 5 ฮอร์โมน: caution, curiosity, affinity, sleepiness, sickness
sickness = สภาวะภายใน (จุ่มเซนเซอร์ความชื้นลงน้ำ = ป่วย) ไม่สั่งท่าตรงๆ
แต่ไปปรับผลของฮอร์โมนตัวอื่นใน behavior.Modulator.resolve (sickness behavior)
ตัวเลขทั้งหมดเป็นค่าตั้งต้น ต้องจูนกับของจริง
"""
import math
from dataclasses import dataclass


class Hormone:
    """H ใน [0, 1] ; อัปเดตทุกรอบ slow loop"""

    def __init__(self, name, alpha, beta, gamma):
        assert 0.0 < alpha < 1.0 and beta >= 0.0 and gamma >= 0.0 and beta + gamma < 1.0
        self.name, self.alpha, self.beta, self.gamma = name, alpha, beta, gamma
        self.h = 0.0
        self.last_update = None

    def update(self, stimulus, now):
        s = min(max(stimulus, 0.0), 1.0)                 # stimulus ต้องผ่าน validate มาแล้ว
        production = self.alpha * s * (1.0 - self.h)     # soft saturation
        clearance = self.beta * self.h
        binding = self.gamma * self.h
        self.h = min(max(self.h + production - clearance - binding, 0.0), 1.0)  # clamp ทุกรอบ
        self.last_update = now
        return self.h

    def reset(self, value=0.0):
        self.h = value

    def equilibrium(self, s):
        return self.alpha * s / (self.alpha * s + self.beta + self.gamma)

    def half_life_steps(self):
        k = self.beta + self.gamma
        return math.inf if k == 0 else math.log(0.5) / math.log(1.0 - k)


def decay_rate_for_half_life(half_life_s, dt):
    """คืนค่า beta + gamma ที่ให้ครึ่งชีวิตตามต้องการ ; dt = เวลาต่อรอบ"""
    n = half_life_s / dt
    return 1.0 - 0.5 ** (1.0 / n)


def alpha_for_equilibrium(h_target, s, k):
    """alpha ที่ทำให้ H นิ่งที่ h_target เมื่อ stimulus = s ; k = beta + gamma"""
    assert 0.0 < h_target < 1.0 and s > 0.0
    return h_target * k / (s * (1.0 - h_target))


def receptor(h, sensitivity=1.0, threshold=0.0):
    """แปลง H -> effect 0..1 ; H ต่ำกว่า threshold ไม่มีผล"""
    assert 0.0 <= threshold < 1.0
    if h <= threshold:
        return 0.0
    return min(1.0, sensitivity * (h - threshold) / (1.0 - threshold))


def ahm_health(hormone, now, quiet_time, timeout, stuck_time):
    h = hormone.h
    if h is None or not math.isfinite(h) or not (0.0 <= h <= 1.0):
        return "FAULT_VALUE"
    if hormone.last_update is None or now - hormone.last_update > timeout:
        return "FAULT_STALE"
    if h > 0.95 and quiet_time > stuck_time:
        return "FAULT_STUCK"
    return "OK"


@dataclass
class HormoneSpec:
    name: str
    half_life_s: float        # ครึ่งชีวิตตอนไม่มีสิ่งเร้า (วินาทีจริง ที่ speed = 1)
    h_star: float             # H ที่จะนิ่งอยู่เมื่อ S = 1 (เหลือที่ว่างไว้เหนือเพดานนี้)
    gamma_share: float = 0.3  # สัดส่วนของ clearance ที่เป็น receptor binding
    threshold: float = 0.1    # receptor: H ต่ำกว่านี้ไม่มีผล
    sensitivity: float = 1.0
    care_half_life_s: float = None   # ถ้ามีสิ่งเร้า "care" (ลูบหัว) ฮอร์โมนนี้ลดลงเร็วขึ้นด้วยครึ่งชีวิตนี้


# ค่าตั้งต้นของโคม: ตกใจขึ้นเร็วลืมเร็ว / อุ่นใจขึ้นช้าลืมช้า
DEFAULT_SPECS = (
    HormoneSpec("caution",   half_life_s=4.0,  h_star=0.80, threshold=0.10),
    HormoneSpec("curiosity", half_life_s=10.0, h_star=0.70, threshold=0.10),
    HormoneSpec("affinity",  half_life_s=40.0, h_star=0.70, threshold=0.10),
    HormoneSpec("sleepiness", half_life_s=25.0, h_star=0.80, threshold=0.05),
    # ป่วยเร็ว (จุ่มน้ำ ~10 วิ ถึงครึ่ง) หายช้า (ครึ่งชีวิต 90 วิ) ลูบหัวช่วยให้หายเร็วขึ้น (15 วิ)
    HormoneSpec("sickness",  half_life_s=90.0, h_star=0.90, threshold=0.05, care_half_life_s=15.0),
)


class HormoneBank:
    """รวมฮอร์โมนทุกตัว อัปเดตพร้อมกันทุกรอบ slow loop

    speed > 1 = เร่งเวลาของฮอร์โมน (ไว้ลองเล่น) ; speed < 1 = ช้าลง
    stimulus = None หมายถึง "ไม่รู้" (เซนเซอร์เสีย) : ไม่สร้างฮอร์โมน แค่ปล่อยให้สลายตามธรรมชาติ
    """

    def __init__(self, specs=DEFAULT_SPECS, slow_dt=0.1, speed=1.0, now=0.0):
        dt = slow_dt * speed
        self.hormones, self.specs = {}, {}
        self.quiet = {}              # เวลาต่อเนื่องที่ไม่มีสิ่งเร้า (ไว้ตรวจ FAULT_STUCK)
        self.slow_dt = slow_dt
        self.speed = speed
        for sp in specs:
            k = decay_rate_for_half_life(sp.half_life_s, dt)
            alpha = alpha_for_equilibrium(sp.h_star, 1.0, k)
            self.hormones[sp.name] = Hormone(sp.name, alpha, beta=(1 - sp.gamma_share) * k,
                                             gamma=sp.gamma_share * k)
            self.specs[sp.name] = sp
            self.quiet[sp.name] = 0.0
        self.hormones_started = now

    def update(self, stimuli, now):
        care = stimuli.get("care") or 0.0
        care = min(max(care, 0.0), 1.0) if care == care else 0.0      # NaN -> 0
        for name, hm in self.hormones.items():
            s = stimuli.get(name)
            hm.update(0.0 if s is None else s, now)
            hl = self.specs[name].care_half_life_s
            if hl and care > 0.0:                                     # การดูแลเร่งให้ลดลง (ไม่มีวันติดลบ)
                hm.h *= 0.5 ** (care * self.slow_dt * self.speed / hl)
            if s is None or s < 0.02:
                self.quiet[name] += self.slow_dt
            else:
                self.quiet[name] = 0.0

    def levels(self):
        return {n: h.h for n, h in self.hormones.items()}

    def effects(self):
        return {n: receptor(h.h, sp.sensitivity, sp.threshold)
                for (n, h), sp in zip(self.hormones.items(), self.specs.values())}

    def health(self, now, timeout=0.5, stuck_time=10.0):
        """คืน {ชื่อ: สถานะ} เฉพาะตัวที่ไม่ OK"""
        bad = {}
        for n, h in self.hormones.items():
            st = ahm_health(h, now, self.quiet[n], timeout, stuck_time)
            if st != "OK":
                bad[n] = st
        return bad

    def reset_all(self):
        for h in self.hormones.values():
            h.reset(0.0)
