"""โคมจำลอง 5 DOF (ฝั่ง "fast loop") : ControlPacket -> CPG + ท่า -> shaping -> Actuator Safety -> มุมข้อต่อ + ไฟ

โค้ดส่วนนี้คือสิ่งที่ต่อไปจะย้ายไปรันบน ESP32 ตอนนี้รันบนโน้ตบุ๊กเพื่อดูผลบนหน้าจอ
  - เป็นทางเดียวที่ผลิตมุมข้อต่อ (single writer) ผ่าน ActuatorSafety เสมอ
  - แพ็กเก็ตเก่าเกินกำหนด -> ใช้ SAFE_PARAMS + โหมด Blind (ไม่รอสมอง)

ข้อต่อ (องศา)
  yaw         หมุนฐาน (+ = ไปทางซ้าย)
  shoulder    มุมแขนล่างจากแนวดิ่ง (+ = เอนไปข้างหน้า)
  elbow       มุมแขนบนสัมพัทธ์กับแขนล่าง (+ = พับไปข้างหน้า)
  head_pitch  มุมหัวสัมพัทธ์กับแขนบน (+ = ก้มลง)
  head_roll   เอียงหัวรอบแกนมอง
"""
import math
from dataclasses import dataclass

from protocol import ControlPacket, SAFE_PARAMS, PACKET_STALE_S

JOINTS = ("yaw", "shoulder", "elbow", "head_pitch", "head_roll")


def clamp(x, lo, hi):
    return min(max(x, lo), hi)


# ================================================================ CPG (หัวข้อ 4.1)
class SO2CPG:
    """o1' = tanh(w11*o1 + w12*o2), o2' = tanh(w21*o1 + w22*o2)
    w11 = w22 = alpha*cos(phi), w12 = alpha*sin(phi), w21 = -alpha*sin(phi)"""
    def __init__(self, phi=0.1, alpha=1.01):
        self.phi, self.alpha = phi, alpha
        self.o1, self.o2 = 0.1, 0.0           # ห้ามเริ่มที่ (0, 0)

    def step(self):
        c = self.alpha * math.cos(self.phi)
        s = self.alpha * math.sin(self.phi)
        self.o1, self.o2 = (math.tanh(c * self.o1 + s * self.o2),
                            math.tanh(-s * self.o1 + c * self.o2))
        return self.o1, self.o2


CPG_DT = 0.02          # CPG อัปเดต 50 Hz
CPG_BASE_HZ = 0.35     # จังหวะ "หายใจ" ที่ tempo = 1
CPG_NORM = 0.2         # แอมพลิจูดจริงของ o1/o2 ที่ alpha = 1.01 (ตรวจใน test_lamp.py)


# ================================================================ Actuator Safety Interface (หัวข้อ 11)
@dataclass
class JointLimits:
    soft_min: float
    soft_max: float
    max_rate: float     # องศา/วินาที (slew-rate)


LIMITS = {   # ช่วงจริงที่วัดได้จากหุ่น
    "yaw":        JointLimits(-90, 90, 240),
    "shoulder":   JointLimits(-80, 30, 200),
    "elbow":      JointLimits(-39, 172, 240),
    "head_pitch": JointLimits(-56, 100, 300),
    "head_roll":  JointLimits(-30, 30, 320),
}


class ActuatorSafety:
    """ทางเดียวที่คำสั่งจะไปถึงมอเตอร์ ; measured = มุมจริงจาก encoder (ในซิม = มุมที่สั่งรอบก่อน)"""
    def __init__(self, limits, cmd_timeout=0.3):
        self.limits, self.cmd_timeout = limits, cmd_timeout
        self.prev = {}
        self.resync = set()

    def filter(self, joint, target, cmd_time, measured, now, dt):
        lim = self.limits[joint]
        fresh = (target is not None and math.isfinite(target)
                 and now - cmd_time <= self.cmd_timeout)
        if not fresh:
            self.resync.add(joint)
            target = measured                                  # คำสั่งเสีย/เก่า -> ค้างท่า ไม่ตัดไฟ
        elif joint in self.resync:
            self.prev[joint] = measured                        # กลับมา: ไล่จากมุมจริง ไม่ใช่คำสั่งเก่า
            self.resync.discard(joint)
        target = clamp(target, lim.soft_min, lim.soft_max)     # angle clamping
        base = self.prev.get(joint, measured)
        max_step = lim.max_rate * dt
        cmd = base + clamp(target - base, -max_step, max_step)  # slew-rate limiting
        self.prev[joint] = cmd
        return cmd


# ================================================================ ท่าตามโหมด
#            yaw  shoulder elbow head_pitch roll
POSES = {   # ตรงกับ motion.py บนบอร์ด (สอนท่าจากหุ่นจริง tools.teach)
    "Idle":    (0,  -61,   148,   83,        0),
    "Curious": (0,   25,    84,   86,        0),
    "Engage":  (0,  -66,   167,   69,        0),
    "Fear":     (0,  -66,   167,  -51,        0),
    "Sleep":   (0,  -73,   167,  -23,       25),
    "Blind":   (0,  -64,   148,   83,        0),
    "Peek":    (0,  -73,   167,   97,       -6),
    "Sick":    (0,  -66,   160,   60,       10),
}
GAZE_W = {"Idle": 0.35, "Curious": 1.0, "Engage": 1.0, "Fear": 0.0, "Sleep": 0.0, "Blind": 0.0, "Peek": 0.0, "Sick": 0.0}
ROLL_AMP = {"Idle": 1.0, "Curious": 3.5, "Engage": 2.5, "Fear": 0.5, "Sleep": 0.3, "Blind": 0.0, "Peek": 0.3, "Sick": 0.3}
FEEL = {   # (ความไว omega_scale, damping zeta)  zeta < 1 = มี overshoot (ความเด้งแบบการ์ตูน)
    "Idle": (1.0, 0.70), "Curious": (0.4, 1.00), "Engage": (0.5, 0.90),
    "Fear": (1.3, 0.50), "Sleep": (0.5, 1.00), "Blind": (0.6, 1.00), "Peek": (0.6, 1.00), "Sick": (0.4, 1.00),
}
BASE_OMEGA = {"yaw": 9.0, "shoulder": 10.0, "elbow": 11.0, "head_pitch": 16.0, "head_roll": 18.0}

ENTER_KICKS = {    # ตรงกับ motion.py บนบอร์ด
    "Fear":     {"shoulder": -170, "elbow": +60, "head_pitch": -150},
    "Engage":  {"shoulder": +45, "head_pitch": +90},
    "Wake":    {"shoulder": +70, "elbow": +40, "head_pitch": -90},
    "Sleep":   {"elbow": +20, "head_pitch": -50},
}

LEAN_SHOULDER, LEAN_ELBOW, LEAN_HEAD = 18.0, 8.0, 4.0
BRIGHTNESS_CAP = 0.95          # เพดานความสว่าง (กันแยงตาคน)
COOL = (205, 225, 255)
WARM = (255, 185, 100)
AMBER = (255, 150, 40)


class Lamp:
    def __init__(self, now=0.0):
        self.cpg = SO2CPG()
        self._acc = 0.0
        self.safety = ActuatorSafety(LIMITS)
        self.angles = dict(zip(JOINTS, POSES["Idle"]))
        self.vel = {j: 0.0 for j in JOINTS}        # ความเร็วของ shaping (spring-damper)
        self.shaped = dict(self.angles)            # ตำแหน่งหลัง shaping ก่อนเข้า safety
        self.mode, self.prev_mode = "Idle", "Idle"
        self.gaze_w = 0.0
        self.avert = 1.0
        self.last_gaze = None
        self.stale = False
        self.light = {"rgb": (255, 200, 120), "intensity": 0.5}
        self._light_f = [0.5, 0.5]                 # brightness, warmth (กรองให้นุ่ม)
        self.targets = dict(self.angles)

    # ------------------------------------------------------------ ภายใน
    def _advance_cpg(self, dt, tempo):
        self.cpg.phi = 2 * math.pi * CPG_BASE_HZ * tempo * CPG_DT
        self._acc += dt
        n = 0
        while self._acc >= CPG_DT and n < 10:
            self.cpg.step()
            self._acc -= CPG_DT
            n += 1
        if n == 10:
            self._acc = 0.0
        return self.cpg.o1 / CPG_NORM, self.cpg.o2 / CPG_NORM

    def _on_mode_change(self, mode, prev):
        key = "Wake" if (prev == "Sleep" and mode != "Sleep") else mode
        for j, v in ENTER_KICKS.get(key, {}).items():
            self.vel[j] += v
        if mode == "Fear":
            self.vel["yaw"] += 160.0 * self.avert

    def _compose(self, mode, P, gaze, x1, x2, dt):
        base = dict(zip(JOINTS, POSES[mode]))
        amp, lean = P["amp"], P["lean"]

        def sig(off):                  # สัญญาณ CPG ที่เลื่อนเฟสต่อข้อต่อ (ให้การเคลื่อนไหวเป็นคลื่น ไม่ใช่ก้อนเดียว)
            return math.cos(off) * x1 + math.sin(off) * x2

        shoulder = base["shoulder"] + lean * LEAN_SHOULDER + amp * 2.0 * sig(0.0)
        elbow = base["elbow"] - lean * LEAN_ELBOW + amp * 2.5 * sig(0.9)
        head = base["head_pitch"] - lean * LEAN_HEAD + amp * 3.5 * sig(1.8)
        yaw = base["yaw"] + amp * 5.0 * sig(2.6)
        roll = base["head_roll"] + amp * ROLL_AMP[mode] * sig(1.2)

        # ทิศมองจากกล้อง
        want_w = clamp(GAZE_W[mode] * P["gaze_follow"], 0.0, 1.0) if gaze is not None else 0.0
        self.gaze_w += (want_w - self.gaze_w) * (1.0 - math.exp(-dt / 0.25))
        if gaze is not None:
            self.last_gaze = gaze
            if abs(gaze[0]) > 3.0:
                self.avert = -1.0 if gaze[0] > 0 else 1.0      # ตอนขี้อายจะหันหนีไปอีกฝั่ง
        w = self.gaze_w
        if self.last_gaze is not None and w > 1e-3:
            yaw_g, pitch_g = self.last_gaze
            head_needed = (90.0 - pitch_g) - (shoulder + elbow)   # มุมหัวที่ทำให้มองตรงระดับสายตา
            yaw = (1 - w) * yaw + w * yaw_g
            head = (1 - w) * head + w * head_needed
        if mode == "Fear":
            yaw += 25.0 * self.avert
        return {"yaw": yaw, "shoulder": shoulder, "elbow": elbow,
                "head_pitch": head, "head_roll": roll}

    def _shape(self, targets, mode, tempo, dt):
        """spring-damper : x'' = w^2 (target - x) - 2 z w x'  (ให้ overshoot แบบ Pixar ได้)"""
        om_s, zeta = FEEL[mode]
        n = max(1, int(math.ceil(dt / 0.005)))
        h = dt / n
        for j in JOINTS:
            w = BASE_OMEGA[j] * om_s * (0.75 + 0.25 * tempo)
            x, v = self.shaped[j], self.vel[j]
            for _ in range(n):
                a = w * w * (targets[j] - x) - 2 * zeta * w * v
                v += a * h
                x += v * h
            self.shaped[j], self.vel[j] = x, v

    def _update_light(self, mode, P, now, dt):
        k = 1.0 - math.exp(-dt / 0.25)
        self._light_f[0] += (clamp(P["brightness"], 0.0, BRIGHTNESS_CAP) - self._light_f[0]) * k
        self._light_f[1] += (clamp(P["warmth"], 0.0, 1.0) - self._light_f[1]) * k
        b, wm = self._light_f
        rgb = tuple(c + (w - c) * wm for c, w in zip(COOL, WARM))
        if mode == "Blind":            # แจ้งว่ากล้อง/สมองมีปัญหา: เหลืองอำพันหรี่ๆ เต้นช้า (ไม่ใช้แดงกะพริบรัว)
            rgb = AMBER
            b = 0.15 + 0.2 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.5 * now))
        self.light = {"rgb": tuple(int(c) for c in rgb), "intensity": b}

    # ------------------------------------------------------------ รอบ fast loop
    def step(self, dt, now, pkt):
        dt = clamp(dt, 1e-3, 0.1)
        finite = pkt is not None and all(math.isfinite(v) for v in pkt.params.values()) \
            and set(SAFE_PARAMS) <= set(pkt.params)
        self.stale = (not finite) or (now - pkt.t) > PACKET_STALE_S
        if self.stale:                 # สมองเงียบ/แพ็กเก็ตเสีย -> ค่าปลอดภัย ไม่รอใคร
            mode, P, gaze, cmd_t = "Blind", SAFE_PARAMS, None, now
        else:
            mode, P, gaze, cmd_t = pkt.mode, pkt.params, pkt.gaze, now

        if mode != self.mode:
            self.prev_mode, self.mode = self.mode, mode
            self._on_mode_change(mode, self.prev_mode)

        x1, x2 = self._advance_cpg(dt, P["tempo"])
        self.targets = self._compose(mode, P, gaze, x1, x2, dt)
        self._shape(self.targets, mode, P["tempo"], dt)
        for j in JOINTS:
            self.angles[j] = self.safety.filter(j, self.shaped[j], cmd_t, self.angles[j], now, dt)
        self._update_light(mode, P, now, dt)
        return self.angles


# ================================================================ จลนศาสตร์ไปข้างหน้า (ไว้วาดภาพ)
H0, L2, L3, L4, RIM = 0.12, 0.50, 0.50, 0.26, 0.17


def forward_kinematics(angles):
    """คืนจุด 3D (X หน้า, Y ซ้าย, Z บน) ของโคม"""
    yaw = math.radians(angles["yaw"])
    phi2 = angles["shoulder"]
    phi3 = phi2 + angles["elbow"]
    phi4 = phi3 + angles["head_pitch"]

    def d(phi):
        r = math.radians(phi)
        return math.sin(r), math.cos(r)          # (หน้า, บน)

    def to3(f, u):
        return (f * math.cos(yaw), f * math.sin(yaw), u)

    p1 = (0.0, H0)
    f2, u2 = d(phi2); p2 = (p1[0] + L2 * f2, p1[1] + L2 * u2)
    f3, u3 = d(phi3); p3 = (p2[0] + L3 * f3, p2[1] + L3 * u3)
    f4, u4 = d(phi4); p4 = (p3[0] + L4 * f4, p3[1] + L4 * u4)
    r4 = math.radians(phi4)
    lateral = (-math.sin(yaw), math.cos(yaw), 0.0)
    perp = (math.cos(r4) * math.cos(yaw), math.cos(r4) * math.sin(yaw), -math.sin(r4))
    roll = math.radians(angles["head_roll"])
    rim_dir = tuple(math.cos(roll) * a + math.sin(roll) * b for a, b in zip(lateral, perp))
    tip = to3(*p4)
    bulb = to3(p3[0] + 0.45 * L4 * f4, p3[1] + 0.45 * L4 * u4)
    return {
        "base": (0.0, 0.0, 0.0), "shoulder": to3(*p1), "elbow": to3(*p2), "head": to3(*p3),
        "tip": tip, "bulb": bulb,
        "rim_a": tuple(t + RIM * r for t, r in zip(tip, rim_dir)),
        "rim_b": tuple(t - RIM * r for t, r in zip(tip, rim_dir)),
        "gaze_elev": 90.0 - phi4,
    }
