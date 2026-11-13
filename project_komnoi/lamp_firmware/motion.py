"""สร้างท่าของโคม: CPG -> ท่าตามโหมด -> spring-damper shaping
พอร์ตมาจาก lamp.py ของฝั่งโน้ตบุ๊ก ให้ผลเหมือนกัน แต่ไม่ใช้ dataclass/f-string หนักๆ
"""
import math

from joints import NAMES, JOINT_BY_NAME, clamp

CPG_DT = 0.02
CPG_BASE_HZ = 0.35
CPG_NORM = 0.2

# ท่าตามโหมด (องศา) -- ข้อต่อไหนไม่มีในหุ่นจริงก็แค่ไม่ถูกใช้
_ORDER = ("yaw", "shoulder", "elbow", "head_pitch", "head_roll")
# shoulder + = เอนไปหน้า, elbow + = พับไปหน้า, head_pitch + = ก้มลง (เหมือน lamp.py)
# ช่วงที่ใช้: yaw -90..90, shoulder -45..30 (แรงไม่พอเกินนี้), elbow -35..65, head_pitch -56..87
# ทุกท่าเหลือขอบอย่างน้อย ~8 องศา เผื่อการแกว่งของ CPG และ overshoot
_POSE_ROWS = {
    "Idle":    (0, -61, 148,  83,  0),   # ผู้ใช้สอนท่า (tools.teach): ทรง Z ลึก
    "Curious": (0,  25,  84,  86,  0),   # สอนท่า 83 -> 86 เงยมองหน้าคน (head_pitch ค่ามาก = เงย เทียบกับแขน ; ขีด 88)
    "Engage":  (0, -66, 167,  69,  0),   # สอนท่า ; หัว 62->69 ล็อกสายตา (-66+167+69=170)
    "Fear":     (0, -66, 167, -51,  0),   # สอนท่า: แขนเท่า Engage หัวเงย
    "Sleep":   (0, -73, 167, -23, 25),   # สอนท่า: หัวเอียง 25
    "Blind":   (0, -64, 148,  83,  0),   # Idle เอนหลังเพิ่ม 3
    "Protect": (0, -61, 148,  83,  0),   # = Idle
    "Peek":    (0, -73, 167,  97, -6),   # หลับแล้วแอบดู: ผู้ใช้จัดหัวเอง (tools.teachhead) เงย 102 หน้าตรง -> ใช้ 97 เผื่อขอบ
    "Sick":    (0, -66, 160,  60, 10),   # ป่วย: ทรุด หัวห้อย เอียงคอเศร้า (ทิศหน้า 34 ใกล้ Idle) + หนาวสั่นจากความป่วย
}
POSES = {}
for _k in _POSE_ROWS:
    POSES[_k] = dict(zip(_ORDER, _POSE_ROWS[_k]))
GAZE_W = {"Idle": 0.35, "Curious": 1.0, "Engage": 1.0, "Fear": 0.0,
          "Sleep": 0.0, "Blind": 0.0, "Protect": 0.0, "Peek": 0.0, "Sick": 0.0}
# head_roll (เซอร์โวใหม่) ใช้ได้ +-30 ; แกว่งแค่ไม่กี่องศาให้ดูมีชีวิต
ROLL_AMP = {"Idle": 1.0, "Curious": 3.5, "Engage": 2.5, "Fear": 0.5,
            "Sleep": 0.3, "Blind": 0.0, "Protect": 0.0, "Peek": 0.3, "Sick": 0.3}
# Curious/Engage: แขนเหวี่ยงไกล (shoulder ~90 องศา) -> ผู้ใช้: "พุ่งแรงเกิน" -> ช้าลงและไม่เด้ง (zeta ~1)
FEEL = {"Idle": (1.0, 0.70), "Curious": (0.4, 1.0), "Engage": (0.5, 0.9),
        "Fear": (1.3, 0.50), "Sleep": (0.5, 1.0), "Blind": (0.6, 1.0), "Protect": (0.8, 1.0),
        "Peek": (0.6, 1.0), "Sick": (0.4, 1.0)}
FAST_JOINTS = ("yaw", "head_roll")
# หัวนำ ตัวตาม (Curious/Engage): เอียงคอ = -K x (ทิศที่สั่ง - ทิศฐานตอนนี้) ไม่เกิน MAX ; ฐานตามช้าลง YAW_FOLLOW
LEAD_ROLL_K, LEAD_ROLL_MAX, YAW_FOLLOW = 2.5, 18.0, 0.5
BASE_OMEGA = {"yaw": 9.0, "shoulder": 10.0, "elbow": 11.0, "head_pitch": 16.0, "head_roll": 18.0}
# ความเร็วที่เติมให้ตอนเข้าโหมด -> ได้ anticipation/overshoot แบบการ์ตูน
# ค่าลดลงจากเดิมเพราะช่วงข้อต่อของหุ่นตัวนี้แคบ ถ้าแรงไปจะไปกระแทก soft limit
ENTER_KICKS = {
    "Fear":     {"shoulder": -170, "elbow": 60, "head_pitch": -150},  # ท่าสอน: หัวเงย -> กระตุกหัวขึ้น
    "Engage":  {"shoulder": 45, "head_pitch": 90},                   # พยักหน้า
    "Wake":    {"shoulder": 70, "elbow": 40, "head_pitch": -90},
    "Sleep":   {"elbow": 20, "head_pitch": -50},                      # ท่าสอน: ทิศตามท่าใหม่
}
PHASE = {"shoulder": 0.0, "elbow": 0.9, "head_pitch": 1.8, "yaw": 2.6, "head_roll": 1.2}
BREATH = {"shoulder": 2.0, "elbow": 2.5, "head_pitch": 3.5, "yaw": 5.0}
LEAN_SHOULDER, LEAN_ELBOW, LEAN_HEAD = 18.0, 8.0, 4.0
# เต้นตอน Engage (ผูกพัน): โยกหัว + พยัก + ส่ายฐานเบาๆ
# ความเร็วสูงสุด: yaw ~11, พยัก ~17 องศา/วิ (ต่ำกว่าเกณฑ์ "ขยับตัวเอง" 30 ของสมอง) ; โยกหัว (roll) ไม่เปลี่ยนทิศเซนเซอร์
DANCE_HZ, DANCE_ROLL, DANCE_NOD, DANCE_YAW = 0.9, 14.0, 4.5, 4.0   # ผู้ใช้: เต้นแรงขึ้นหน่อย (roll 8->14, nod 3->4.5)
# ป่วยให้เห็นชัด (ความป่วย = 1 - warmth ที่สมองส่งมา): หัวห้อย + หนาวสั่น (เอียงคอสั่นเร็วๆ เบาๆ)
SICK_DROOP, SICK_SHIVER, SICK_SHIVER_HZ = 18.0, 5.0, 3.5   # 5 Hz โดน spring กรองเหลือ +-1 -> 3.5 Hz +-5
DANCE_S = 4.0           # ผู้ใช้: เต้นนานไป -> เต้นแค่ตอนเพิ่งเข้า Engage แล้วผ่อนจนหยุด


class SO2CPG:
    def __init__(self, phi=0.1, alpha=1.01):
        self.phi, self.alpha = phi, alpha
        self.o1, self.o2 = 0.1, 0.0          # ห้ามเริ่มที่ (0, 0)

    def step(self):
        c = self.alpha * math.cos(self.phi)
        s = self.alpha * math.sin(self.phi)
        self.o1, self.o2 = (math.tanh(c * self.o1 + s * self.o2),
                            math.tanh(-s * self.o1 + c * self.o2))
        return self.o1, self.o2


class MotionEngine:
    def __init__(self, start_angles):
        self.cpg = SO2CPG()
        self.acc = 0.0
        self.shaped = dict(start_angles)
        self.vel = {}
        for n in NAMES:
            self.vel[n] = 0.0
        self.mode = "Idle"
        self.gaze_w = 0.0
        self.avert = 1.0
        self.last_gaze = None
        self.t = 0.0                    # นาฬิกาของท่าเต้นตอน Engage
        self.dance_until = -1.0

    def set_from_measured(self, angles):
        """ใช้ตอนบูตหรือหลังปลดล็อก: เริ่มไล่จากมุมจริง ไม่ใช่คำสั่งเก่า"""
        for n in NAMES:
            if angles.get(n) is not None:
                self.shaped[n] = angles[n]
                self.vel[n] = 0.0

    def _advance_cpg(self, dt, tempo):
        self.cpg.phi = 2 * math.pi * CPG_BASE_HZ * tempo * CPG_DT
        self.acc += dt
        n = 0
        while self.acc >= CPG_DT and n < 10:
            self.cpg.step()
            self.acc -= CPG_DT
            n += 1
        if n == 10:
            self.acc = 0.0
        return self.cpg.o1 / CPG_NORM, self.cpg.o2 / CPG_NORM

    def _on_mode_change(self, mode, prev):
        key = "Wake" if (prev == "Sleep" and mode != "Sleep") else mode
        kicks = ENTER_KICKS.get(key)
        if kicks:
            for j in kicks:
                if j in self.vel:
                    self.vel[j] += kicks[j]
        if mode == "Engage":
            self.dance_until = self.t + DANCE_S
        if mode == "Fear" and "yaw" in self.vel:
            self.vel["yaw"] += 160.0 * self.avert

    def _compose(self, mode, P, gaze, x1, x2, dt):
        """สร้างมุมเป้าหมายของข้อต่อที่ "มีจริง" เท่านั้น (ตาม JOINTS ใน config.py)
        ข้อต่อที่ยังไม่ได้ประกอบจะถูกข้ามไป ไม่พัง"""
        base = POSES[mode]
        amp, lean = P["amp"], P["lean"]
        out = {}
        for n in NAMES:
            off = PHASE.get(n, 0.0)
            sig = math.cos(off) * x1 + math.sin(off) * x2
            swing = BREATH.get(n, ROLL_AMP[mode] if n == "head_roll" else 0.0)
            out[n] = base.get(n, 0.0) + amp * swing * sig
        if "shoulder" in out:
            out["shoulder"] += lean * LEAN_SHOULDER
        if "elbow" in out:
            out["elbow"] -= lean * LEAN_ELBOW
        if "head_pitch" in out:
            # head_pitch ค่ามาก = เงย (เทียบกับแขน) ; ทิศหน้า = shoulder + elbow - head
            # ชดเชยให้หน้าชี้ทิศเดิมตอนโน้ม แล้วเงยเพิ่มอีก LEAN_HEAD (โน้มเข้าหา = เงยมอง, ถอยกลัว = ก้มหลบ)
            out["head_pitch"] += lean * (LEAN_SHOULDER - LEAN_ELBOW + LEAN_HEAD)

        self.t += dt
        sick = 1.0 - min(1.0, max(0.0, P.get("warmth", 1.0)))
        if sick > 0.1 and mode not in ("Fear", "Blind", "Protect"):
            if "head_pitch" in out and mode not in ("Sleep", "Peek"):   # ท่าหลับห้อยอยู่แล้ว
                out["head_pitch"] -= SICK_DROOP * sick                    # หัวห้อย (head_pitch น้อย = ก้ม)
            if "head_roll" in out:                     # หนาวสั่นแบบเป็นไข้ หลับก็ยังสั่น ("ง่วงแบบป่วยๆ") ; roll ไม่เปลี่ยนทิศเซนเซอร์
                out["head_roll"] += SICK_SHIVER * sick * math.sin(2 * math.pi * SICK_SHIVER_HZ * self.t)
        left = self.dance_until - self.t
        if mode == "Engage" and left > 0.0:
            # ผูกพัน = เต้นเบาๆ แว้บเดียว ด้วยข้อต่อเบา (ไม่ใช้ shoulder ที่แรงน้อย) ; ผ่อนลงช่วง 1.5 วิสุดท้าย
            env = min(1.0, left / 1.5, (DANCE_S - left) / 0.4)
            ph = 2 * math.pi * DANCE_HZ * self.t
            if "head_roll" in out:
                out["head_roll"] += env * DANCE_ROLL * math.sin(ph)
            if "head_pitch" in out:
                out["head_pitch"] += env * DANCE_NOD * math.sin(ph + 1.0)
            if "yaw" in out:
                out["yaw"] += env * DANCE_YAW * math.sin(0.5 * ph)

        want = clamp(GAZE_W[mode] * P["gaze_follow"], 0.0, 1.0) if gaze is not None else 0.0
        self.gaze_w += (want - self.gaze_w) * (1.0 - math.exp(-dt / 0.25))
        if gaze is not None:
            self.last_gaze = gaze
            if abs(gaze[0]) > 3.0:
                self.avert = -1.0 if gaze[0] > 0 else 1.0
        w = self.gaze_w
        if self.last_gaze is not None and w > 1e-3:
            yaw_g, _pitch_g = self.last_gaze
            # มองตาม = หมุนฐานอย่างเดียว (สมองกวาดหาคนด้วย gaze yaw) ; ไม่ยุ่ง head_pitch
            # (โค้ดเดิมปรับหัวตามกล้อง ใช้สูตรทิศหัวผิด ทำให้หน้าก้ม -- เลิกใช้กล้องแล้ว)
            if "yaw" in out:
                out["yaw"] = (1 - w) * out["yaw"] + w * yaw_g
        if (mode in ("Curious", "Engage") and "yaw" in out and "head_roll" in out
                and self.last_gaze is not None and w > 0.5):
            # หัวนำ ตัวตาม: ฐานยังหันไม่ถึงเท่าไร เอียงคอนำไปทางนั้นเท่านั้น ; ฐานถึงแล้วคอตั้งตรงเอง
            # yaw + = ซ้ายของโคม, roll + = เอียงขวา -> หันซ้ายต้องเอียงซ้าย (roll ลบ)
            # (โคมนี้ไม่มีข้อต่อหันหัวซ้ายขวา ลำแสงหมุนตามฐานเท่านั้น ; roll เป็นท่าทางให้คนเห็น)
            err = self.last_gaze[0] - self.shaped.get("yaw", out["yaw"])   # เฉพาะการหันตาม ไม่นับการแกว่งหายใจ
            lead = max(-LEAD_ROLL_MAX, min(LEAD_ROLL_MAX, -LEAD_ROLL_K * err))
            out["head_roll"] += lead
        if mode == "Fear" and "yaw" in out:
            out["yaw"] += 25.0 * self.avert
        return out

    def _shape(self, targets, mode, tempo, dt):
        om_s, zeta = FEEL[mode]
        n = int(dt / 0.005) + 1
        h = dt / n
        for j in NAMES:
            # yaw (มองตาม) และ roll (เต้น) ต้องไวเสมอ แม้ท่าแขนจะค่อยๆ โน้มช้า
            s = max(om_s, 1.0) if j in FAST_JOINTS else om_s
            if j == "yaw" and mode in ("Curious", "Engage"):
                s *= YAW_FOLLOW                 # ตัวตามช้ากว่าหัว ให้เห็นจังหวะหัวนำ
            z = min(zeta, 0.9) if j in FAST_JOINTS else zeta
            w = BASE_OMEGA[j] * s * (0.75 + 0.25 * tempo)
            x, v = self.shaped[j], self.vel[j]
            tg = targets[j]
            for _ in range(n):
                v += (w * w * (tg - x) - 2 * z * w * v) * h
                x += v * h
            self.shaped[j], self.vel[j] = x, v

    def step(self, dt, mode, P, gaze):
        if mode != self.mode:
            prev, self.mode = self.mode, mode
            self._on_mode_change(mode, prev)
        x1, x2 = self._advance_cpg(dt, P["tempo"])
        targets = self._compose(mode, P, gaze, x1, x2, dt)
        self._shape(targets, mode, P["tempo"], dt)
        return self.shaped

    def hold(self, dt):
        """ค้างท่าปัจจุบัน (ใช้ตอน Protect/E-stop): หยุดความเร็ว ไม่ขยับต่อ"""
        for n in NAMES:
            self.vel[n] = 0.0
        return self.shaped
