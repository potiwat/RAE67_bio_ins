"""สมองของโคม (slow loop ~10 Hz): stimulus -> ฮอร์โมน -> Bounded Modulation -> arbiter + FSM -> ControlPacket

กฎจาก design notes ที่ใช้ในไฟล์นี้
  - ฮอร์โมนและ FSM ส่งได้แค่ "พารามิเตอร์" ผ่าน Bounded Modulation Interface (clamp + จำกัดอัตราเปลี่ยน)
  - เหตุการณ์เข้าทาง arbiter ทางเดียว (priority + timestamp + State Guard)
  - ข้อมูลเสียไม่เท่ากับปกติ : กล้องเสียนานเกินกำหนด -> โหมด Blind + safe default + แจ้งเตือน
"""
import math
from copy import deepcopy
from dataclasses import dataclass, field

from ahm import HormoneBank
from perception import PerceptionEngine, PerceptionConfig, HysteresisAbove, clamp
from protocol import ControlPacket, SAFE_PARAMS


# ================================================================ Bounded Modulation Interface (หัวข้อ 6)
@dataclass
class ParamSpec:
    base: float        # ค่าปกติ (ไม่มีฮอร์โมนมีผล)
    lo: float          # ช่วงปลอดภัย
    hi: float
    max_step: float    # slew-rate ของพารามิเตอร์ ต่อรอบ slow loop
    gains: dict        # {ฮอร์โมน: การเปลี่ยนค่าเมื่อ effect = 1}
    value: float = None


PARAM_SPECS = {
    #                 base  lo   hi    step  caution curiosity affinity sleepiness
    "tempo":       ParamSpec(1.0, 0.3, 1.6, 0.04, {"caution": -0.4, "curiosity": +0.5, "affinity": -0.2, "sleepiness": -0.6, "sickness": -0.6}),
    "amp":         ParamSpec(1.0, 0.3, 1.5, 0.04, {"caution": -0.5, "curiosity": +0.35, "affinity": -0.2, "sleepiness": -0.6, "sickness": -0.6}),
    "lean":        ParamSpec(0.0, -1.0, 1.0, 0.10, {"caution": -1.0, "curiosity": +0.8, "affinity": +0.5, "sleepiness": -0.3, "sickness": -0.7}),
    "gaze_follow": ParamSpec(0.8, 0.0, 1.2, 0.10, {"caution": -1.0, "curiosity": +0.2, "affinity": +0.1, "sleepiness": -0.8, "sickness": -0.3}),
    "brightness":  ParamSpec(0.8, 0.2, 0.95, 0.05, {"caution": -0.15, "curiosity": +0.1, "affinity": +0.15, "sleepiness": -0.55, "sickness": -0.35}),
    # warmth = "ความแข็งแรง" (ใช้ช่องเดิมของโปรโตคอล): 1 = สีอารมณ์ปกติ, 0 = ป่วยหนัก สีซีด ; สีหลักมาจากโหมด (led.EMOTION_RGB)
    "warmth":      ParamSpec(1.0, 0.0, 1.0, 0.05, {"sickness": -1.0}),
}


class Modulator:
    def __init__(self, specs=None):
        self.specs = deepcopy(specs or PARAM_SPECS)
        for s in self.specs.values():
            s.value = clamp(s.base, s.lo, s.hi)

    @staticmethod
    def resolve(effects):
        """ตัดสินเมื่อฮอร์โมนขัดกัน (หัวข้อ 5.4): caution กดทั้ง curiosity และ affinity
        ทำที่นี่ ไม่ใช่ป้อนฮอร์โมนกลับเข้าฮอร์โมน จึงไม่เกินวง positive feedback"""
        e = dict(effects)
        # ป่วย (sickness behavior): ไม่อยากรู้อยากเห็น ง่วงง่าย ตกใจง่ายกว่าปกติ
        # ปรับที่ effect ไม่ป้อนกลับเข้าฮอร์โมน -> ไม่มีวง feedback
        k = e.get("sickness", 0.0)
        if k > 0.0:
            e["curiosity"] = e.get("curiosity", 0.0) * (1.0 - 0.7 * k)
            e["sleepiness"] = min(1.0, e.get("sleepiness", 0.0) + 0.5 * k)
            e["caution"] = min(1.0, e.get("caution", 0.0) * (1.0 + 0.5 * k))
        c = e.get("caution", 0.0)
        e["curiosity"] = e.get("curiosity", 0.0) * (1.0 - c)
        e["affinity"] = e.get("affinity", 0.0) * (1.0 - 0.5 * c)
        return e

    @staticmethod
    def _move(spec, target):
        target = clamp(target, spec.lo, spec.hi)                        # bounds
        step = clamp(target - spec.value, -spec.max_step, spec.max_step)  # slew-rate
        spec.value += step

    def update(self, effects):
        e = self.resolve(effects)
        for sp in self.specs.values():
            self._move(sp, sp.base + sum(g * e.get(h, 0.0) for h, g in sp.gains.items()))
        return self.values()

    def force_safe(self):
        """ตอน fault: ค่อยๆ ไปที่ค่าปลอดภัย (ยังจำกัดอัตราเปลี่ยนอยู่)"""
        for name, sp in self.specs.items():
            self._move(sp, SAFE_PARAMS[name])
        return self.values()

    def values(self):
        return {n: s.value for n, s in self.specs.items()}


# ================================================================ Arbiter + FSM (หัวข้อ 9, 10)
PRIORITY = {            # เลขน้อย = สำคัญกว่า
    "sensor_lost": 1, "sensor_ok": 1, "hormone_fault": 1,
    "startle": 2, "startle_clear": 2,
    "sick": 3, "sick_clear": 3, "exhausted": 3,   # ป่วยมาก่อนอารมณ์ทั่วไป (ตกใจยังแทรกได้ เป็นรีเฟล็กซ์)
    "target_seen": 4, "target_engaged": 4, "target_lost": 4, "wake": 4, "affinity_low": 4,
    "sleepy": 5,
}


@dataclass
class Event:
    kind: str
    timestamp: float            # เวลาของ "ข้อมูล" ที่ใช้ตัดสิน
    priority: int = None

    def __post_init__(self):
        if self.priority is None:
            self.priority = PRIORITY[self.kind]


TRANSITIONS = {         # (สถานะปัจจุบัน, เหตุการณ์) -> สถานะใหม่ ; "*" = จากทุกสถานะ
    ("*", "sensor_lost"): "Blind",
    ("Blind", "sensor_ok"): "Idle",
    ("*", "startle"): "Fear",
    ("Fear", "startle_clear"): "Idle",
    ("Idle", "target_seen"): "Curious",
    ("Sleep", "target_seen"): "Idle",
    ("Curious", "target_engaged"): "Engage",
    ("Engage", "affinity_low"): "Curious",       # ผูกพันจางลง (อิ่มแล้ว) -> กลับไปแค่สนใจ
    # ป่วยมาก่อน: อารมณ์ไหนก็ตาม ป่วยหนักพอ -> ป่วย ; ระหว่างป่วยไม่สนใจ/ไม่ผูกพัน จนกว่าจะหาย
    ("Idle", "sick"): "Sick", ("Curious", "sick"): "Sick", ("Engage", "sick"): "Sick",
    ("Sick", "sick_clear"): "Idle",
    ("Sick", "sleepy"): "Sleep",                 # ง่วงแบบป่วยๆ (บอร์ดยังซีด/สั่นตอนหลับ)
    # ตื่นมา 12 ชม. = หมดแรง หลับแม้มีคน
    ("Idle", "exhausted"): "Sleep", ("Curious", "exhausted"): "Sleep",
    ("Engage", "exhausted"): "Sleep", ("Sick", "exhausted"): "Sleep",
    ("Curious", "target_lost"): "Idle",
    ("Engage", "target_lost"): "Idle",
    ("Idle", "sleepy"): "Sleep",
    ("Sleep", "wake"): "Idle",
}

GUARD = {               # State Guard: priority "เลขสูงสุด" ที่ยอมให้เปลี่ยนสถานะได้
    "Idle": 5, "Curious": 5, "Sleep": 5,
    "Engage": 4,        # ระหว่างเล่นกับคน ถ้าง่วงต้องรอ
    "Fear": 2,           # ระหว่างตกใจ รับแค่เรื่องตกใจ/ความปลอดภัย
    "Sick": 5,           # ป่วย: เปลี่ยนได้แค่ตามที่ TRANSITIONS กำหนด (หาย / หลับ / ตกใจ)
    "Blind": 1,         # กล้องเสีย รับแค่เรื่องความปลอดภัย
}


class Arbiter:
    def __init__(self, stale_limit=0.5):
        self.stale_limit = stale_limit
        self.last_state_change = -math.inf

    def mark_state_change(self, now):
        self.last_state_change = now

    def candidates(self, events, now, allowed_max_priority):
        valid = []
        for e in events:
            is_safety = e.priority <= 1
            stale = (now - e.timestamp > self.stale_limit) or (e.timestamp < self.last_state_change)
            if stale and not is_safety:
                continue                       # คิดจากข้อมูลเก่า -> ทิ้ง รอค่าใหม่รอบหน้า (กัน race condition)
            if e.priority <= allowed_max_priority:
                valid.append(e)                # ผ่าน State Guard
        return sorted(valid, key=lambda e: (e.priority, -e.timestamp))


class BehaviorFSM:
    def __init__(self, arbiter, min_dwell, start="Idle", now=0.0):
        self.arbiter, self.min_dwell = arbiter, min_dwell
        self.state, self.since = start, now
        self.prev_state = start

    def step(self, events, now):
        for ev in self.arbiter.candidates(events, now, GUARD[self.state]):
            target = TRANSITIONS.get((self.state, ev.kind)) or TRANSITIONS.get(("*", ev.kind))
            if target is None or target == self.state:
                continue
            if ev.priority > 1 and now - self.since < self.min_dwell:
                continue                       # อยู่ไม่ครบเวลาขั้นต่ำ (กันสลับรัว) ยกเว้นเรื่องความปลอดภัย
            self.prev_state, self.state, self.since = self.state, target, now
            self.arbiter.mark_state_change(now)
            break
        return self.state


# ================================================================ LampBrain
@dataclass
class BrainConfig:
    slow_dt: float = 0.1
    min_dwell: float = 1.2
    blind_limit_s: float = 2.0         # กล้องเสียเกินนี้ -> Blind
    arbiter_stale_s: float = 0.5
    reflex_enter: float = 0.65         # S ของ caution ที่ทำให้สะดุ้งทันที (0.75 -> 0.65 ผู้ใช้: กลัวสำคัญกว่าสนใจ)
    reflex_release: float = 0.40
    startle_h_enter: float = 0.40      # หรือฮอร์โมน caution สะสมถึงระดับนี้ (0.55 -> 0.40)
    startle_h_release: float = 0.22
    engage_affinity: float = 0.28      # ผู้ใช้: เร็วไป (0.15) -> ช้าไป (0.35) -> เร็วขึ้นหน่อย 0.28
    engage_after_s: float = 4.0        # ต้องสนใจมาก่อนอย่างน้อยเท่านี้ (6 -> 4)
    engage_bored: float = 0.20         # Engage แล้วความผูกพันลดต่ำกว่านี้ (อิ่มแล้ว) -> กลับไปแค่สนใจ
    curious_min_h: float = 0.15        # สนใจได้เมื่อความอยากรู้ขึ้นถึงเท่านี้ด้วย (0.20 -> 0.15 ผู้ใช้: เร็วขึ้นหน่อย)
    sleep_min_s: float = 480.0         # หลับแล้วความง่วงค้าง 8 นาที จึงค่อยๆ ลดจนตื่นเอง
    sick_sleep_extra: float = 1.0      # ป่วยตอนเข้านอน -> นอนนานขึ้น x (1 + ป่วย x ค่านี้) : ป่วยเต็มที่ 16 นาที
    sick_sleep_drive: float = 0.5      # ป่วยแล้วง่วงง่าย: เพิ่มสิ่งเร้าง่วง = ความป่วย x ค่านี้
    sick_curiosity_cut: float = 1.6    # ป่วยแล้วสนใจยาก: ความอยากรู้ที่ใช้ตัดสิน x (1 - ระดับป่วย x ค่านี้) ; ป่วย 40% = สนใจแทบไม่ได้
    rested_s: float = 120.0            # ตื่นเองแล้ว "สดชื่น" ไม่ง่วงจากการอยู่คนเดียวอีกช่วงหนึ่ง
    sick_enter: float = 0.45           # ป่วยเกินนี้ -> สถานะป่วย (มาก่อนอารมณ์อื่น)
    sick_release: float = 0.25         #   หายเหลือต่ำกว่านี้ -> กลับเป็นปกติ
    awake_full_s: float = 12 * 3600.0  # ตื่นนานเท่านี้ แรงกดดันให้นอนเต็ม (sleep pressure) -> หลับแม้มีคน
    pressure_drive: float = 0.5        # แรงกดดันเต็มที่ = สิ่งเร้าง่วงเท่า "ไม่มีใครอยู่"
    sleepy_enter: float = 0.60
    sleepy_release: float = 0.25
    target_min_dwell: float = 2.0      # เห็นต่อเนื่องเท่านี้ถึงสนใจ (0.6 เร็วไป -> 3 ช้าไป -> 2)
    pose_change_s: float = 3.0         # เปลี่ยนท่าใช้เวลาประมาณนี้ (Sleep ทรุดช้า) -> ตัวรับรู้ไม่นับระยะที่เปลี่ยนเพราะตัวเอง
    peek_every_s: float = 20.0         # หลับแล้วทุกกี่วินาทีจะ "แอบดู" (ท่า Peek: เงยแค่หัว) หาคน
    peek_look_s: float = 3.0           # หลังเงยเสร็จ มองนานเท่านี้ ไม่เจอใครก็ก้มหลับต่อ
    track_patience_s: float = 0.15     # มองตาม: หลุดจากลำแสงนานเท่านี้ -> เริ่มหาใกล้ๆ (เห็นอยู่ = จ้องนิ่ง)
    tgt_tol_m: float = 0.05            # ระยะต่างจากเป้าเกินนี้ (หรือ 12%) = คนละสิ่ง (มือยื่นจากอกไม่ถึงคืบก็แยกได้)
    tgt_tol_rel: float = 0.12
    scan_speed_dps: float = 25.0       # กวาดช้ากว่าเกณฑ์ "ขยับตัวเอง" (30) -> ยังอ่านระยะได้ระหว่างกวาด
    scan_limit_deg: float = 85.0       # กวาดได้สุดระยะ yaw (ขีด +-90)
    aim_change_deg: float = 40.0       # หัวเปลี่ยนทิศเกินนี้ = "หันไปทางอื่น" ; ทิศหน้า: Idle 4, Curious 23, Engage 32, Peek 11 | Sleep 117, Fear 152


# หลุดแล้วหาใกล้จุดที่เห็นล่าสุดก่อน (องศา เทียบทิศที่เห็นล่าสุด) ส่ายกว้างขึ้นเรื่อยๆ
LOCAL_SEARCH = (10.0, -10.0, 25.0, -25.0, 45.0, -45.0)


def _sgn(x):
    return 1.0 if x >= 0 else -1.0


def _head_aim(state):
    """ทิศที่หน้าโคมชี้ของท่านั้น ; None ถ้าไม่รู้
    ทดสอบบนหุ่นจริงแล้ว: head_pitch ค่ามาก = หน้าเงยขึ้นเทียบกับแขน (ตรงข้ามกับ shoulder/elbow)
    จึงเป็น shoulder + elbow - head_pitch (ค่ามาก = หน้าก้มลงไปทางพื้น)"""
    try:
        from lamp import POSES
    except Exception:
        return None
    row = POSES.get(state) or (POSES.get("Idle") if state == "Protect" else None)
    return None if row is None else float(row[1] + row[2] - row[3])


class LampBrain:
    def __init__(self, speed=1.0, cfg=None, perception_cfg=None, alert=None, now=0.0, perception=None):
        """perception = ตัวรับรู้ที่หน้าตาเหมือน PerceptionEngine (เช่น SensorPerception) ; None = กล้อง"""
        self.cfg = cfg or BrainConfig()
        self.speed = speed
        self.perception = perception or PerceptionEngine(perception_cfg, speed=speed, now=now)
        self.bank = HormoneBank(slow_dt=self.cfg.slow_dt, speed=speed, now=now)
        self.modulator = Modulator()
        self.fsm = BehaviorFSM(Arbiter(self.cfg.arbiter_stale_s), self.cfg.min_dwell, now=now)
        self.reflex = HysteresisAbove(self.cfg.reflex_enter, self.cfg.reflex_release)
        self.startle_h = HysteresisAbove(self.cfg.startle_h_enter, self.cfg.startle_h_release)
        self.sleepy_h = HysteresisAbove(self.cfg.sleepy_enter, self.cfg.sleepy_release)
        self.sick_h = HysteresisAbove(self.cfg.sick_enter, self.cfg.sick_release)
        self._awake_since = now                # แรงกดดันให้นอน: นับตั้งแต่ตื่นครั้งล่าสุด (นอนครบแล้วนับใหม่)
        self.alert = alert or (lambda msg: print("[ALERT]", msg))
        self.alerts = []                       # (เวลา, ข้อความ) ล่าสุด
        self.seq = 0
        self.last = {}                         # snapshot ล่าสุด ไว้ให้ viewer/ทดสอบอ่าน
        self._peek_start = None                # เวลาเริ่มแอบดู (None = ไม่ได้แอบดู)
        self._next_peek = None
        self._out_mode = None                  # ท่าที่ส่งไปโคมล่าสุด (อาจต่างจาก state ตอนแอบดู)
        self._gaze_yaw = 0.0                   # มองตาม: ทิศที่สั่งหมุนฐาน (องศา, + = ซ้ายของโคม)
        self._seen_yaw = 0.0                   # ทิศที่เห็นเป้าหมายล่าสุด
        self._search_i = None                  # กำลังหาใกล้ๆ ขาที่เท่าไร (None = ไม่ได้หา)
        self._tgt_d = None                     # ระยะของเป้าที่จ้องอยู่ (แยกมือออกจากตัวคนข้างหลัง)
        self._rested_until = None              # ตื่นเองหลังนอนครบ -> ไม่ง่วงซ้ำจนถึงเวลานี้
        self.pressure = 0.0
        self._sleep_started = None
        self._sleep_len = self.cfg.sleep_min_s
        self._lost_since = None
        self._scan_dir = 1.0
        self._scan_turns = 0
        self.searching = False
        self._fault_flag = False

    # -------------------------------------------------------------- ต่อเฟรม (เร็ว)
    def on_frame(self, frame, now):
        return self.perception.update(frame, now)

    def _alert(self, msg, now):
        self.alerts.append((now, msg))
        self.alerts = self.alerts[-5:]
        self.alert(msg)

    # -------------------------------------------------------------- มองตาม (active sensing)
    def _tgt_tol(self):
        """ระยะต่างเท่าไรถึงนับว่าเป็นคนละสิ่ง (มือ 0.45 vs ตัว 0.6 ม.)"""
        return max(self.cfg.tgt_tol_m, self.cfg.tgt_tol_rel * (self._tgt_d or 0.0))

    def _track(self, p, now):
        """มองตาม (active sensing) -- เซนเซอร์บนหัวรู้แค่ระยะ ไม่รู้ทิศ
        เห็นอยู่ = ค้างนิ่งจ้องไว้ (ไม่ส่ายเอง ; ผู้ใช้: ส่ายเป็นแพตเทิร์น ไม่เหมือนตามมือ)
        หลุด track_patience_s -> หาใกล้จุดที่เห็นล่าสุดก่อน ส่ายกว้างขึ้นเรื่อยๆ (LOCAL_SEARCH)
        -> ไม่เจอ กวาดเต็มระยะสองฝั่ง -> ไม่เจอ ปล่อยให้ target_lost
        คืน True = ยังถือว่ามีเป้าหมาย ห้ามส่ง target_lost"""
        c = self.cfg
        dt = c.slow_dt * self.speed
        if self.fsm.state in ("Curious", "Engage") and not p.valid:
            return True                            # อัลตร้าโซนิคหายแวบหนึ่ง: ค้างทิศเดิมไว้ (บั๊กเดิม: รีเซ็ตหันตรง -> หลุด)
        tracking = self.fsm.state in ("Curious", "Engage") and p.valid
        hold = False
        seen = p.valid and getattr(p, "in_beam", p.present)
        # ล็อกที่ "ระยะ" ของเป้าด้วย: มือเลื่อนออก ลำแสงไปเจอตัวคนข้างหลัง (ไกลกว่า) = เป้าหลุด
        # (บั๊กจริง: ตัวคน/โต๊ะอยู่ในระยะตลอด -> นับว่ายังเห็น -> ไม่หันตามเลย "หัน +0")
        d = getattr(self.perception, "d_med", None)
        if seen and d is not None and tracking:
            if self._tgt_d is None or d < self._tgt_d - self._tgt_tol():
                self._tgt_d = d                        # เป้าใหม่ หรือมีอะไรใกล้กว่าเข้ามา -> จ้องสิ่งที่ใกล้กว่า
            elif d > self._tgt_d + self._tgt_tol():
                seen = False                           # ไกลกว่าเป้าชัดๆ = เห็นของข้างหลัง เป้าหลุดไปแล้ว
            elif abs(d - self._tgt_d) < 0.5 * self._tgt_tol():
                self._tgt_d += 0.15 * (d - self._tgt_d)  # ตามระยะที่ค่อยๆ เปลี่ยน (เฉพาะค่าที่ใกล้มาก ไม่ให้ตัวคนลากไป)
        if not tracking:
            self._tgt_d = None
            self.searching, self._lost_since, self._search_i = False, None, None
            if self.fsm.state != "Fear":           # Fear ใช้ทิศเดิมหันหนี ; ท่าอื่นกลับมามองตรง
                self._gaze_yaw = 0.0
                self._seen_yaw = 0.0
        elif seen:                                 # เห็นอยู่: จ้องนิ่ง จำทิศไว้
            self.searching, self._lost_since, self._search_i = False, None, None
            self._seen_yaw = self._gaze_yaw
        else:
            if self._lost_since is None:
                self._lost_since = now
            hold = True
            if (now - self._lost_since) * self.speed >= c.track_patience_s:
                self.searching = True
                step = c.scan_speed_dps * dt
                if self._search_i is None:
                    self._search_i = 0
                if self._search_i == len(LOCAL_SEARCH) and p.present and self._tgt_d is not None:
                    # หาใกล้ๆ ไม่เจอ แต่ยังมีคนอยู่ในลำแสง -> กลับไปจ้องที่เดิม แล้วล็อกสิ่งที่เห็นตรงนั้นแทน
                    self._gaze_yaw = self._seen_yaw
                    self._tgt_d = None
                    self.searching, hold, self._search_i, self._lost_since = False, True, None, None
                elif self._search_i < len(LOCAL_SEARCH):        # หาใกล้ๆ ก่อน ส่ายกว้างขึ้นเรื่อยๆ
                    tgt = self._seen_yaw + LOCAL_SEARCH[self._search_i]
                    tgt = max(-c.scan_limit_deg, min(c.scan_limit_deg, tgt))
                    err = tgt - self._gaze_yaw
                    self._gaze_yaw += max(-step, min(step, err))
                    if abs(err) <= step:
                        self._search_i += 1
                        if self._search_i == len(LOCAL_SEARCH):  # เตรียมกวาดเต็มระยะ ไปทางที่ไกลกว่า
                            self._scan_dir = -_sgn(self._gaze_yaw)
                            self._scan_turns = 0
                else:                                           # กวาดเต็มระยะสองฝั่ง
                    self._gaze_yaw += self._scan_dir * step
                    if abs(self._gaze_yaw) >= c.scan_limit_deg:
                        self._gaze_yaw = _sgn(self._gaze_yaw) * c.scan_limit_deg
                        self._scan_dir = -_sgn(self._gaze_yaw)
                        self._scan_turns += 1
                    if self._scan_turns >= 2:                   # ครบสองฝั่ง ไม่เจอใคร
                        self.searching, hold, self._search_i = False, False, None
                        self._gaze_yaw = self._seen_yaw = 0.0
        scan = getattr(self.perception, "scanning", None)
        if scan is not None:
            self.perception.scanning = self.searching
        return hold

    # -------------------------------------------------------------- ทุก 0.1 วินาที (ช้า)
    def tick(self, now):
        c = self.cfg
        p = self.perception.percept
        S = self.perception.stimuli(p)
        # ---- นอนหลับ 8 นาที: ระหว่างหลับความง่วงค้าง ครบแล้วค่อยๆ ลดจนตื่นเอง ; ตื่นแล้วสดชื่นช่วงหนึ่ง
        sick_now = self.bank.hormones["sickness"].h
        if self.fsm.state == "Sleep":
            asleep = (now - self.fsm.since) * self.speed
            S["sleepiness"] = 1.0 if asleep < self._sleep_len else 0.0   # ป่วยตอนเข้านอน -> นอนนานขึ้น
        else:
            if self._rested_until is not None and now < self._rested_until:
                if (S.get("sleepiness") or 0.0) <= 0.5:   # ไม่ง่วงจากการอยู่คนเดียว (กล่อมนอนปุ่ม 6 ยังได้ผล)
                    S["sleepiness"] = 0.0
            # ป่วยแล้วง่วงง่าย (sickness behavior) -- แม้เพิ่งตื่นมาสดชื่นก็ตาม
            S["sleepiness"] = min(1.0, (S.get("sleepiness") or 0.0) + c.sick_sleep_drive * sick_now)
        # ---- แรงกดดันให้นอน (12 ชม.): ตื่นนานเท่าไรง่วงสะสมเท่านั้น แม้มีคนอยู่ด้วย
        self.pressure = min(1.0, (now - self._awake_since) * self.speed / c.awake_full_s)
        if self.fsm.state != "Sleep":
            S["sleepiness"] = max(S.get("sleepiness") or 0.0, c.pressure_drive * self.pressure)
        self.bank.update(S, now)
        hook = getattr(self.perception, "after_hormones", None)
        if hook is not None:                   # ผลครั้งเดียวของปุ่ม (ปลุก/ดุ) -- ก่อนอ่านระดับฮอร์โมน
            hook(self.bank)

        bad = self.bank.health(now)            # ฮอร์โมนพัง? (ห้ามพังเงียบ)
        if bad:
            for n, st in bad.items():
                self._alert(f"AHM {n}: {st}", now)
            self.bank.reset_all()
            self._fault_flag = True
        else:
            self._fault_flag = False
        H, E = self.bank.levels(), self.bank.effects()

        reflex_active = False
        if p.valid:
            reflex_active = self.reflex.update(S["caution"] or 0.0)
            if reflex_active:                  # reflex เร็วกว่าฮอร์โมน: ท่าสะดุ้งต้องมาพร้อมพารามิเตอร์ "ระแวง" ทันที
                E["caution"] = max(E["caution"], 0.8)

        hold_target = self._track(p, now)       # มองตาม/กวาดหา (Curious, Engage)
        if hasattr(self.perception, "protect_target"):
            self.perception.protect_target = self.fsm.state == "Engage"   # ผูกพันอยู่ ห้ามจำคนเป็นฉากหลัง

        events = []
        if p.blind_time > c.blind_limit_s:
            events.append(Event("sensor_lost", now))
        elif p.valid:
            events.append(Event("sensor_ok", now))
        if p.valid:
            t = p.t
            humoral = self.startle_h.update(H["caution"])
            events.append(Event("startle" if (reflex_active or humoral) else "startle_clear", t))
            # ป่วยแล้วสนใจยาก: ใช้ความอยากรู้ที่โดนความป่วยกดแล้วตัดสิน (ไม่ใช่แค่ท่าทาง)
            cur_eff = H["curiosity"] * max(0.0, 1.0 - c.sick_curiosity_cut * H["sickness"])
            if (p.present and p.dwell >= c.target_min_dwell
                    and (cur_eff >= c.curious_min_h or self.fsm.state == "Sleep")):
                events.append(Event("target_seen", t))
            in_state = (now - self.fsm.since) * self.speed
            if (p.present and p.facing and H["affinity"] > c.engage_affinity
                    and self.fsm.state == "Curious" and in_state >= c.engage_after_s):
                events.append(Event("target_engaged", t))
            if self.fsm.state == "Engage" and H["affinity"] < c.engage_bored:
                events.append(Event("affinity_low", t))
            if not p.present and not hold_target:   # กำลังกวาดหา -> ยังไม่นับว่าคนหายไป
                events.append(Event("target_lost", t))
            sleepy = self.sleepy_h.update(H["sleepiness"])
            exhausted = sleepy and self.pressure >= 1.0
            if sleepy and not p.present:
                events.append(Event("sleepy", t))
            if exhausted:
                events.append(Event("exhausted", t))      # ตื่นมาครบ 12 ชม.: หลับแม้มีคน
            if (p.present and not exhausted) or not sleepy:
                events.append(Event("wake", t))          # หมดแรงอยู่ มีคนมาก็ไม่ตื่น (ปุ่ม 5 ยังปลุกได้)
            if self.sick_h.update(H["sickness"]):
                events.append(Event("sick", t))
            else:
                events.append(Event("sick_clear", t))

        before = self.fsm.state
        state = self.fsm.step(events, now)
        # ---- หลับ: หลับตา (ไม่รับรู้ระยะ) + แอบดูเป็นระยะ (เงยท่า Idle มอง peek_look_s แล้วก้มกลับ)
        if state == "Sleep":
            if before != "Sleep" or self._next_peek is None:
                self._next_peek = now + c.peek_every_s / self.speed
                self._peek_start = None
            if self._peek_start is None and now >= self._next_peek:
                self._peek_start = now
            elif (self._peek_start is not None
                  and now >= self._peek_start + (c.pose_change_s + c.peek_look_s) / self.speed):
                self._peek_start = None            # ไม่เจอใคร -> ก้มหลับต่อ (ความง่วงไม่ลด)
                self._next_peek = now + c.peek_every_s / self.speed
        else:
            self._peek_start = self._next_peek = None
        peeking = state == "Sleep" and self._peek_start is not None
        set_eyes = getattr(self.perception, "set_eyes", None)
        if set_eyes is not None:
            set_eyes(state == "Sleep" and not peeking, now)
        out_mode = "Peek" if peeking else state     # เงยแค่หัว แขนท่า Sleep เดิม
        if out_mode != self._out_mode:
            notify = getattr(self.perception, "on_self_motion", None)
            if notify is not None and self._out_mode is not None:
                # efference copy: บอกตัวรับรู้ว่ากำลังจะเปลี่ยนท่า และหัวจะหันไปไหม (เทียบท่าที่ส่งจริง)
                a0, a1 = _head_aim(self._out_mode), _head_aim(out_mode)
                aim_changed = a0 is None or a1 is None or abs(a1 - a0) > c.aim_change_deg
                notify(now, self.cfg.pose_change_s, aim_changed)
            self._out_mode = out_mode
        if before != state:
            if before == "Sleep":              # ตื่นแล้ว ความง่วงหายไปส่วนหนึ่ง (FSM ปรับฮอร์โมน ไม่ใช่มอเตอร์)
                slept = (now - self._sleep_started) * self.speed if self._sleep_started is not None else 0.0
                self.bank.hormones["sleepiness"].h *= 0.4
                if slept >= c.sleep_min_s:         # นอนครบ ตื่นเอง -> สดชื่น ; แรงกดดันให้นอนนับใหม่
                    self._rested_until = now + c.rested_s / self.speed
                    self._awake_since = now
            if state == "Sleep":
                self._sleep_started = now
                self._sleep_len = c.sleep_min_s * (1.0 + c.sick_sleep_extra * self.bank.hormones["sickness"].h)
            self.last_transition = (now, before, state)
            if state == "Blind":               # ห้ามพังเงียบ
                self._alert(f"sensor data invalid > {c.blind_limit_s:.0f}s -> Blind (safe defaults)", now)
            elif before == "Blind":
                self._alert("sensor data back -> resuming", now)

        if state == "Blind" or self._fault_flag:
            params = self.modulator.force_safe()
        else:
            params = self.modulator.update(E)

        if state in ("Curious", "Engage") and out_mode == state:
            gaze = (self._gaze_yaw, 0.0)          # หมุนฐานไปทางที่เจอคน / กำลังกวาดหา
        elif state == "Fear" and abs(self._gaze_yaw) > 3.0:
            gaze = (self._gaze_yaw, 0.0)          # บอกทิศคนให้บอร์ดหันหนี (avert)
        else:
            gaze = p.gaze if (p.valid and p.present and state != "Blind") else None
        self.seq += 1
        pkt = ControlPacket(t=now, mode=out_mode, params=params, gaze=gaze, seq=self.seq)
        self.last = {"percept": p, "S": S, "H": H, "E": E, "state": state, "peek": peeking,
                     "gaze_yaw": self._gaze_yaw, "searching": self.searching,
                     "awake_h": (now - self._awake_since) * self.speed / 3600.0, "pressure": self.pressure,
                     "params": params, "events": [e.kind for e in events], "packet": pkt}
        return pkt
