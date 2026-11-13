"""ชั้นรับรู้: ผลตรวจจับจากกล้อง -> Percept -> stimulus (0..1) ของฮอร์โมนทั้ง 4

ลำดับตามหัวข้อ 3 ของ design notes: validate -> low-pass -> hysteresis/debounce
หลักสำคัญ: ข้อมูลเสียต้อง "ไม่รู้" ไม่ใช่ "ไม่มีคน" (Percept.valid = False, stimulus = None)
ไฟล์นี้ไม่ต้องใช้ OpenCV จึงทดสอบแยกได้
"""
import math
from dataclasses import dataclass, field, replace


# ---------------------------------------------------------------- ตัวช่วยจาก design notes (หัวข้อ 3)
@dataclass
class Sample:
    value: float
    timestamp: float


def validate(sample, now, lo, hi, stale_limit, invalid_values=()):
    """คืนค่า float ถ้าใช้ได้, None ถ้าเสีย (ห้ามส่ง None หรือค่าเสียเข้า filter)"""
    if sample is None:
        return None
    v = sample.value
    if v is None or not math.isfinite(v):
        return None
    if v in invalid_values or not (lo <= v <= hi):
        return None
    if now - sample.timestamp > stale_limit:
        return None
    return v


class TimeLowPass:
    """low-pass แบบอิงเวลา: y += (1 - exp(-dt/tau)) * (x - y)  (ไม่ขึ้นกับ fps ของกล้อง)"""
    def __init__(self, tau):
        self.tau, self.y = tau, None

    def update(self, x, dt):
        if self.y is None:
            self.y = x
        else:
            a = 1.0 - math.exp(-max(dt, 0.0) / self.tau)
            self.y += a * (x - self.y)
        return self.y

    def reset(self, value=None):
        self.y = value


class HysteresisAbove:
    """active เมื่อค่า > enter_above และปล่อยเมื่อค่า < release_below (กัน chattering)"""
    def __init__(self, enter_above, release_below):
        assert enter_above > release_below
        self.enter_above, self.release_below = enter_above, release_below
        self.active = False

    def update(self, x):
        if not self.active and x > self.enter_above:
            self.active = True
        elif self.active and x < self.release_below:
            self.active = False
        return self.active

    def reset(self):
        self.active = False


def clamp(x, lo=0.0, hi=1.0):
    return min(max(x, lo), hi)


# ---------------------------------------------------------------- โครงข้อมูล
@dataclass
class Detection:
    cx: float          # จุดกึ่งกลาง 0..1 ในภาพ (ซ้าย -> ขวา)
    cy: float          # 0..1 (บน -> ล่าง)
    h: float           # ความสูงกรอบ / ความสูงภาพ
    kind: str = "face"  # "face" หรือ "body" (blob การเคลื่อนไหว)
    conf: float = 1.0


@dataclass
class FrameInfo:
    t: float                       # เวลาที่ถ่ายภาพ (นาฬิกาเดียวกับ now)
    ok: bool = True                # กล้องส่งภาพมาได้ไหม
    brightness: float = None       # 0..1
    detections: list = field(default_factory=list)
    frozen: bool = False           # ภาพค้าง (กล้องแฮงก์)


@dataclass
class Percept:
    t: float
    valid: bool = False
    present: bool = False
    zone: str = "none"             # none / far / mid / near
    p: float = 0.0                 # "ความใกล้" 0..1+ (1 = ใกล้มาก)
    closing: float = 0.0           # d ln(p)/dt  (บวก = เข้าใกล้)
    rushing: bool = False
    motion: float = 0.0            # ความเร็วของจุดกึ่งกลาง (หน่วยภาพ/วินาที)
    dwell: float = 0.0             # อยู่มานานเท่าไร (วินาที)
    facing: bool = False
    crowd: bool = False
    quiet_time: float = 0.0
    light: float = 0.5
    novelty: float = 0.0
    surprise: float = 0.0
    cx: float = 0.5
    cy: float = 0.5
    gaze: tuple = None             # (yaw_deg, pitch_deg) ; None = ไม่มีเป้าหมาย
    blind_time: float = 0.0


@dataclass
class PerceptionConfig:
    hfov_deg: float = 62.0
    vfov_deg: float = 38.0
    face_near_h: float = 0.40      # ความสูงใบหน้า/ภาพ ที่นับว่า "ใกล้มาก" (p = 1)
    body_near_h: float = 0.95
    frame_stale_s: float = 0.5
    warmup_s: float = 1.5          # หลังเปิดโปรแกรม ยังไม่นับว่า "โผล่มากะทันหัน" (คนนั่งอยู่หน้ากล้องอยู่แล้ว)
    grace_s: float = 0.8           # เป้าหมายหายไปไม่เกินนี้ ยังนับว่าอยู่ (Haar กะพริบ)
    near_enter: float = 0.75
    near_release: float = 0.60
    mid_enter: float = 0.28
    mid_release: float = 0.20
    rush_enter: float = 0.7        # d ln(p)/dt : ~ขนาดตัวเพิ่ม 2 เท่าใน 1 วินาที
    rush_release: float = 0.3
    tau_pos: float = 0.05
    tau_size: float = 0.10
    tau_closing: float = 0.20
    tau_motion: float = 0.15
    tau_light: float = 0.30
    novelty_tau: float = 15.0
    habit_gain: float = 0.2
    habit_half_life: float = 120.0
    affinity_ramp_start: float = 3.0
    affinity_ramp_len: float = 10.0
    quiet_start: float = 12.0
    quiet_ramp: float = 30.0
    dark_level: float = 0.20

    def time_scaled(self, speed):
        """เร่ง/หน่วงเวลาระดับพฤติกรรม (ใช้คู่กับ HormoneBank speed)"""
        return replace(self, novelty_tau=self.novelty_tau / speed,
                       habit_half_life=self.habit_half_life / speed,
                       affinity_ramp_start=self.affinity_ramp_start / speed,
                       affinity_ramp_len=self.affinity_ramp_len / speed,
                       quiet_start=self.quiet_start / speed,
                       quiet_ramp=self.quiet_ramp / speed)


STIMULUS_NAMES = ("caution", "curiosity", "affinity", "sleepiness")


class PerceptionEngine:
    def __init__(self, cfg=None, speed=1.0, now=0.0):
        self.cfg = (cfg or PerceptionConfig()).time_scaled(speed)
        c = self.cfg
        self.lp_cx, self.lp_cy = TimeLowPass(c.tau_pos), TimeLowPass(c.tau_pos)
        self.lp_p = TimeLowPass(c.tau_size)
        self.lp_closing = TimeLowPass(c.tau_closing)
        self.lp_motion = TimeLowPass(c.tau_motion)
        self.lp_light = TimeLowPass(c.tau_light)
        self.near = HysteresisAbove(c.near_enter, c.near_release)
        self.mid = HysteresisAbove(c.mid_enter, c.mid_release)
        self.rush = HysteresisAbove(c.rush_enter, c.rush_release)
        self.last_seen = -math.inf     # ยังไม่เคยเห็นใคร
        self.start = now               # นับ "เงียบ" ตั้งแต่เริ่มโปรแกรม
        self.last_valid = now
        self.was_present = False
        self.visit_start = None
        self.habit, self.visit_habit = 0.0, 0.0
        self.surprise0, self.surprise_t = 0.0, -math.inf
        self.face_seen_t = -math.inf
        self.crowd_until = -math.inf
        self.prev = None               # (t, kind, p_f, cx_f, cy_f) ของการตรวจจับรอบก่อน
        self.prev_update_t = now
        self.cx_f, self.cy_f, self.p_f = 0.5, 0.5, 0.0
        self.percept = Percept(t=now)

    # ------------------------------------------------------------ ตรวจข้อมูลเข้า
    def _clean(self, dets, frame_t, now):
        good = []
        for d in dets:
            cx = validate(Sample(d.cx, frame_t), now, 0.0, 1.0, self.cfg.frame_stale_s)
            cy = validate(Sample(d.cy, frame_t), now, 0.0, 1.0, self.cfg.frame_stale_s)
            h = validate(Sample(d.h, frame_t), now, 0.02, 1.5, self.cfg.frame_stale_s)
            if cx is None or cy is None or h is None or d.kind not in ("face", "body"):
                continue
            good.append(Detection(cx, cy, h, d.kind, d.conf))
        return good

    @staticmethod
    def _pick(dets):
        faces = [d for d in dets if d.kind == "face"]
        pool = faces or dets
        return max(pool, key=lambda d: d.h) if pool else None

    # ------------------------------------------------------------ หลัก
    def update(self, frame, now):
        c = self.cfg
        dt = max(now - self.prev_update_t, 1e-3)
        self.prev_update_t = now
        t_ok = frame.t is not None and math.isfinite(frame.t)
        valid = frame.ok and t_ok and (now - frame.t) <= c.frame_stale_s and not frame.frozen
        if not valid:
            # ข้อมูลเสีย: ไม่รู้ ไม่ใช่ "ปกติ" -> ไม่เปลี่ยนค่าที่ถือไว้ แค่นับเวลาบอด
            old = self.percept
            self.percept = replace(old, valid=False, blind_time=now - self.last_valid)
            return self.percept
        self.last_valid = now

        if frame.brightness is not None and math.isfinite(frame.brightness):
            self.lp_light.update(clamp(frame.brightness), dt)
        light = self.lp_light.y if self.lp_light.y is not None else 0.5

        dets = self._clean(frame.detections, frame.t, now)
        primary = self._pick(dets)
        n_faces = sum(1 for d in dets if d.kind == "face")
        if n_faces >= 2:
            self.crowd_until = now + 1.0

        present = primary is not None or (now - self.last_seen) <= c.grace_s
        new_visit = primary is not None and not self.was_present

        # ความจำเรื่อง "คนผ่านซ้ำๆ" (habituation) สลายตามเวลา
        self.habit *= 0.5 ** (dt / c.habit_half_life)

        if primary is not None:
            kind = primary.kind
            p_raw = primary.h / (c.face_near_h if kind == "face" else c.body_near_h)
            if new_visit:
                for f in (self.lp_cx, self.lp_cy, self.lp_p, self.lp_closing, self.lp_motion):
                    f.reset()
                self.lp_closing.reset(0.0)
                self.lp_motion.reset(0.0)
                self.prev = None
                self.visit_start = now
                self.visit_habit = self.habit
                self.habit = min(1.0, self.habit + c.habit_gain)
            cx_f = self.lp_cx.update(primary.cx, dt)
            cy_f = self.lp_cy.update(primary.cy, dt)
            p_f = self.lp_p.update(p_raw, dt)
            if new_visit:
                # คนโผล่มาใกล้ๆ ทันที = ตกใจ (surprise ลดลงเชิงเส้นใน 1.5 วินาที)
                self.surprise0 = clamp(p_f * 1.3) if (p_f > 0.5 and now - self.start >= c.warmup_s) else 0.0
                self.surprise_t = now
            if self.prev is not None and self.prev[1] == kind and 0 < now - self.prev[0] < 0.3:
                dtd = now - self.prev[0]
                inst_closing = (math.log(max(p_f, 1e-3)) - math.log(max(self.prev[2], 1e-3))) / dtd
                self.lp_closing.update(inst_closing, dtd)
                speed = math.hypot(cx_f - self.prev[3], cy_f - self.prev[4]) / dtd
                self.lp_motion.update(speed, dtd)
            self.prev = (now, kind, p_f, cx_f, cy_f)
            self.cx_f, self.cy_f, self.p_f = cx_f, cy_f, p_f
            self.near.update(p_f)
            self.mid.update(p_f)
            self.rush.update(self.lp_closing.y or 0.0)
            self.last_seen = now
            if kind == "face":
                self.face_seen_t = now

        if not present:
            self.near.reset(); self.mid.reset(); self.rush.reset()
            self.visit_start = None
            self.prev = None
        self.was_present = present

        zone = "none"
        if present:
            zone = "near" if self.near.active else ("mid" if self.mid.active else "far")
        dwell = (now - self.visit_start) if (present and self.visit_start is not None) else 0.0
        novelty = (math.exp(-dwell / c.novelty_tau) * (1.0 - 0.6 * self.visit_habit)) if present else 0.0
        surprise = max(0.0, self.surprise0 * (1.0 - (now - self.surprise_t) / 1.5))
        gaze = None
        if present:
            gaze = ((0.5 - self.cx_f) * c.hfov_deg, (0.5 - self.cy_f) * c.vfov_deg)

        self.percept = Percept(
            t=frame.t, valid=True, present=present, zone=zone,
            p=self.p_f if present else 0.0,
            closing=(self.lp_closing.y or 0.0) if present else 0.0,
            rushing=self.rush.active and present,
            motion=(self.lp_motion.y or 0.0) if present else 0.0,
            dwell=dwell, facing=(now - self.face_seen_t) < 0.6,
            crowd=now < self.crowd_until,
            quiet_time=0.0 if present else max(0.0, now - max(self.last_seen, self.start)),
            light=light, novelty=novelty, surprise=surprise,
            cx=self.cx_f, cy=self.cy_f, gaze=gaze, blind_time=0.0)
        return self.percept

    # ------------------------------------------------------------ Percept -> stimulus
    def stimuli(self, p):
        """คืน {ฮอร์โมน: S 0..1} ; ถ้าข้อมูลเสียคืน None ทุกตัว (ไม่รู้ ≠ ปกติ)"""
        if not p.valid:
            return {n: None for n in STIMULUS_NAMES}
        c = self.cfg
        if p.present:
            prox = clamp((p.p - 0.55) / 0.45)
            rush = clamp(0.5 + 0.5 * p.p) if p.rushing else 0.0
            crowd = 0.4 if p.crowd else 0.0
            caution = max(prox, rush, p.surprise, crowd)

            zone_f = {"far": 0.6, "mid": 1.0, "near": 0.3}.get(p.zone, 0.0)
            motion_f = 1.0 - 0.5 * clamp(p.motion / 0.8)
            curiosity = zone_f * p.novelty * motion_f

            calm = 1.0 - clamp(p.motion / 0.5)
            face_f = 1.0 if p.facing else 0.4
            ramp = clamp((p.dwell - c.affinity_ramp_start) / c.affinity_ramp_len)
            aff_zone = {"far": 0.5, "mid": 1.0, "near": 0.8}.get(p.zone, 0.0)
            affinity = 0.0 if p.rushing else calm * face_f * ramp * aff_zone * (1.0 - caution)
            sleepiness = 0.0
        else:
            caution = curiosity = affinity = 0.0
            s_quiet = clamp((p.quiet_time - c.quiet_start) / c.quiet_ramp)
            s_dark = clamp((c.dark_level - p.light) / 0.15)
            sleepiness = max(s_quiet, s_dark)
        return {"caution": caution, "curiosity": curiosity,
                "affinity": affinity, "sleepiness": sleepiness}
