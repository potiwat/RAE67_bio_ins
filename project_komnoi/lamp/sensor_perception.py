"""รับรู้จากเซนเซอร์บนบอร์ด (แทนกล้อง): ระยะ + ความชื้น + keypad -> Percept + สิ่งเร้า S

อินพุต = telemetry ที่ถอดแล้ว (dict มี dist_m, wet, key, key_seq) + เวลาที่รับ
ใช้กับ LampBrain(perception=SensorPerception()) ได้ทันที เพราะหน้าตาเหมือน PerceptionEngine

ระยะ (อัลตร้าโซนิค)          ใกล้เกิน < 0.2 m -> caution ; 0.2..1.2 m ยิ่งใกล้ curiosity ยิ่งขึ้น
                              อยู่นิ่งใกล้ๆ นาน -> affinity ; พุ่งเข้ามาเร็ว -> caution ; ไม่มีใครนาน -> sleepiness
ความชื้น                      wet 0..1 -> sickness
keypad (ผังปุ่ม 3 แถว)        สิ่งเร้าค้างไว้ KEY_PULSE_S วินาทีหลังกด + ผลครั้งเดียวบางปุ่ม
ข้อมูลเก่า/ไม่รู้ -> None (ไม่สร้างฮอร์โมน) ไม่ใช่ 0 ; ไม่มีระยะนานเกิน -> Blind (ห้ามพังเงียบ)

อัลตร้าโซนิคอยู่บนหัว (เคลื่อนที่ไปกับโคม) จึงมีกลไกกันโคม "กลัวตัวเอง" 2 ชั้น:
  habituation        ระยะที่ค้างนิ่ง (เปลี่ยนไม่เกิน hab_tol_m) -> ความกลัวหายใน ~3 วิ, ความสนใจหายใน ~20 วิ
                     นิ่งนานมาก = ฉากหลัง (โต๊ะ/ผนัง/ตัวเอง) ไม่นับว่ามีคน
  corollary discharge ตอนข้อต่อของโคมเองกำลังขยับ (จาก telemetry) ระยะที่เปลี่ยนเป็นผลจากตัวเอง:
                     ไม่นับเป็นการพุ่งเข้าหา และสิ่งที่เห็นหลังขยับเสร็จถือเป็นฉากหลังทันทีจนกว่าจะเปลี่ยน
"""
from dataclasses import dataclass

from perception import HysteresisAbove, Percept, clamp

# ปุ่ม -> สิ่งเร้า (ค้างไว้ช่วงสั้นๆ หลังกด) ; "care" เร่งให้หายป่วย
KEY_STIMULI = {
    "1": {"affinity": 1.0, "care": 1.0},     # ลูบหัว
    "2": {"affinity": 0.7},                  # ลูบแขน/ตัว
    "3": {"curiosity": 1.0},                 # ทักทาย
    "4": {"care": 1.0},                      # รักษา (ผู้ใช้: เลิกใช้สะกิด) -> ป่วยหายเร็ว
    "5": {},                                 # ปลุก (ผลครั้งเดียว)
    "6": {"sleepiness": 1.0},                # กล่อมนอน
    "7": {"caution": 1.0},                   # ตบหัว -> ถึงเกณฑ์ reflex สะดุ้งทันที
    "8": {"caution": 0.8},                   # ผลัก
    "9": {"caution": 0.6},                   # ดุ
}
KEY_NAMES = {"1": "ลูบหัว", "2": "ลูบตัว", "3": "ทักทาย", "4": "รักษา", "5": "ปลุก",
             "6": "กล่อมนอน", "7": "ตบหัว", "8": "ผลัก", "9": "ดุ"}
# ผลครั้งเดียวต่อฮอร์โมนที่สะสมอยู่ (คูณ) -- ทำใน after_hormones ไม่ป้อนกลับเป็นสิ่งเร้า
KEY_ONESHOT = {"5": {"sleepiness": 0.3}, "9": {"affinity": 0.7}, "4": {"sickness": 0.6}}   # รักษา: ป่วยลดทันที 40%
HORMONES = ("caution", "curiosity", "affinity", "sleepiness", "sickness")


@dataclass
class SensorPerceptConfig:
    tlm_stale_s: float = 0.5        # telemetry เก่ากว่านี้ = ไม่รู้
    too_close_m: float = 0.20
    zone_far_m: float = 0.70        # ขอบนอกของระยะสนใจ (ผู้ใช้: 2 ม. เยอะไป -> 70 ซม.)
    present_release_m: float = 0.85 # hysteresis ของ "มีคน"
    engage_m: float = 0.60          # อยู่ใกล้พอจะผูกพัน (ต้องอยู่ในระยะตรวจจับ)
    calm_mps: float = 0.15          # เคลื่อนช้ากว่านี้ = อยู่นิ่ง
    rush_mps: float = 0.80          # looming: เข้าใกล้เร็วกว่านี้ ...
    loom_m: float = 0.45            #   ... และใกล้กว่านี้ = พุ่งเข้าหา
    fear_speed_lo: float = 0.4      # เข้ามาเร็วกว่านี้ อะดรีนาลีนเริ่มขึ้น (โน้มเข้ามาช้าๆ ไม่กลัว)
    fear_speed_hi: float = 0.9      #   เร็วเท่านี้ = กลัวเต็มที่ (สะดุ้ง)
    alarm_hold_s: float = 3.0       # สัญญาณตกใจค้างอยู่หลังสิ่งเร้าหาย (อะดรีนาลีนค้างในเลือด) แล้วค่อยๆ จาง
    vel_tau_s: float = 0.2          # ความเรียบของความเร็ว (0.4 ช้าไป: ระยะ 70 ซม. เข้ามาเร็วจบใน ~0.5 วิ)
    jump_mps: float = 4.0           # เร็วกว่านี้ไม่ใช่คนพุ่ง แต่เป็น "เป้าหมายเปลี่ยน" (เช่น ผนัง -> คนเดินตัดหน้า)
    affinity_full_s: float = 30.0   # อยู่ด้วยกันนิ่งๆ นานเกินนี้เริ่ม "อิ่ม"
    affinity_fade_s: float = 15.0   #   แล้วสิ่งเร้าหมดใน 15 วิ
    affinity_after_s: float = 2.5   # อยู่นิ่งใกล้ๆ นานเท่านี้ถึงเริ่มอุ่นใจ (3 -> 4 -> 2.5)
    absent_sleepy_s: float = 8.0    # ไม่มีใครนานเท่านี้ถึงเริ่มง่วง
    key_pulse_s: float = 1.5
    hab_tol_m: float = 0.02         # เปลี่ยนไม่เกินนี้ = ยังนิ่งอยู่ (ขั้นต่ำ)
    hab_tol_rel: float = 0.30       # หรือไม่เกิน 30% ของระยะ (ระยะใกล้ อัลตร้าโซนิคแกว่งหลายเซนติเมตร)
    hab_tol_max: float = 0.05       # แต่ไม่เกินนี้ (คนยืนโยกตัว +-4 ซม. ต้องยังนับว่าขยับ)
    hab_win_s: float = 3.0          # ดูช่วงแกว่งของระยะในหน้าต่างนี้
    med_n: int = 5                  # ใช้ค่ากลาง 5 ค่าล่าสุด ตัดค่ากระโดดแวบเดียว
    arrival_m: float = 0.15         # "ประชิด" ต้องเห็นมันเข้ามา: ระยะลดลงอย่างน้อยเท่านี้
    arrival_s: float = 2.0          #   ภายในเวลาเท่านี้ (ของที่วางนิ่งอยู่ใกล้ ไม่ใช่สิ่งที่น่ากลัว)
    hab_caution: tuple = (1.0, 2.0) # (รอก่อนเริ่มชิน, ใช้เวลาชินจนหมด) วินาที -> ความกลัวหายใน 3 วิ
    hab_interest: tuple = (10.0, 10.0)   # ความสนใจหายใน 20 วิ -> แล้วถือเป็นฉากหลัง
    self_move_dps: float = 30.0     # เร็วกว่านี้ = กำลังเปลี่ยนท่า (CPG หายใจสูงสุด ~26 องศา/วิ, เปลี่ยนท่า 200+)
    self_settle_s: float = 0.7      # หลังหยุดขยับ ยังถือว่าเป็นผลจากตัวเองอีกช่วงหนึ่ง
    joint_window_s: float = 0.3     # คิดความเร็วข้อต่อเฉลี่ยช่วงนี้ (บอร์ดอ่านข้อต่อวนทีละตัว ~6 ครั้ง/วิ/ข้อ)
    same_target_m: float = 0.10     # หลังขยับเสร็จ ระยะต่างจากก่อนขยับไม่เกินนี้ = เป้าหมายเดิม
    pre_move_s: float = 0.3         # ย้อนดู "ก่อนขยับ" ไปเท่านี้ (feedback ข้อต่อหน่วงกว่าระยะ)
    present_confirm_s: float = 0.3  # คนเพิ่งโผล่ ต้องเห็นต่อเนื่องเท่านี้ก่อนนับว่ามีคน
    present_hold_s: float = 0.8     # ลำแสงหลุดจากคนไม่เกินนี้ ยังนับว่ามีคน (ตอนส่ายมองตาม ลำแสงข้ามขอบคนบ่อย)
    curiosity_gain: float = 0.9
    curiosity_base: float = 0.35    # อยู่ขอบนอกของระยะก็อยากรู้ได้ระดับนี้
    # ความคุ้นเคยกับสถานที่ (background map): จำระยะฉากหลังแยกตามทิศ -> คน = ใกล้กว่าฉากหลังชัดๆ
    bg_unknown_m: float = 2.6       # ทิศที่ยังไม่เคยเห็น ถือว่าฉากหลังอยู่ไกลเท่านี้ (นอกระยะสนใจ)
    bg_yaw_bin: float = 5.0         # แยกทิศฐานทุก 5 องศา
    bg_aim_bin: float = 15.0        # แยกมุมก้มเงยของหน้า (shoulder+elbow-head) ทุก 15 องศา
    bg_margin_m: float = 0.25       # ใกล้กว่าฉากหลังอย่างน้อยเท่านี้ (หรือ 15%) ถึงนับว่า "ใหม่"
    bg_margin_rel: float = 0.15
    bg_learn_far: float = 0.3       # เห็นไกลกว่าที่จำ -> ฉากหลังอยู่ไกลกว่านั้นแน่ จำทันที (ต่อเฟรม)
    bg_learn_near_s: float = 30.0   # ของวางใหม่ (ใกล้กว่าที่จำ) ค่อยๆ จำเป็นฉากหลัง ~30 วิ (ตอนไม่มีคน)
    bg_stat_tau_s: float = 4.0      # ความแปรปรวนของระยะในแต่ละทิศ (เฉลี่ยช่วงนี้)
    bg_still_std_m: float = 0.015   # แกว่งน้อยกว่านี้ = นิ่งสนิทแบบสิ่งของ (คนหายใจ/โยก แกว่งมากกว่า)
    bg_still_s: float = 12.0        # นิ่งสนิทนานเท่านี้ -> จำเป็นฉากหลังได้แม้เคยนับว่ามีคน
    bg_learn_still_s: float = 8.0   #   แล้วจำเร็วขึ้น


class SensorPerception:
    def __init__(self, cfg=None, speed=1.0, now=0.0):
        self.cfg = cfg or SensorPerceptConfig()
        self.speed = speed
        self.percept = Percept(t=now)
        self.present_h = HysteresisAbove(-self.cfg.zone_far_m, -self.cfg.present_release_m)
        self.dist = None
        self.wet = None
        self.vel = 0.0                 # m/s (ลบ = เข้าใกล้)
        self._last_d = None
        self._last_dt_t = None
        self._t_rx = None
        self._valid_since = None
        self._last_valid = now
        self._present_since = None
        self._absent_since = now
        self._key_seq = None
        self.pulses = []               # [(หมดเวลา, {สิ่งเร้า})]
        self.pending_oneshot = []
        self.presses = []              # (เวลา, ปุ่ม) ไว้ log/แสดงผล
        self._d_ref = None             # habituation: ระยะอ้างอิงตอนเริ่มนิ่ง
        self._hab_win = []             # [(เวลา, ระยะค่ากลาง)] ไว้ดูช่วงแกว่ง
        self._static_since = now
        self._joints_prev = None       # corollary discharge: มุมข้อต่อรอบก่อน
        self._joint_hist = []          # [(เวลา, มุม 4 ข้อต่อ)] ไว้คิดความเร็วเฉลี่ย
        self._history = []             # [(เวลา, (d_ref, static_since, dist))] ~1 วิล่าสุด
        self._raw_since = None         # เริ่มเห็นคน (ยังไม่ยืนยัน) ตั้งแต่เมื่อไร
        self._last_in_beam = -1e9
        self._last_n = []              # ระยะดิบล่าสุด (หาค่ากลาง)
        self._recent = []              # [(เวลา, ระยะค่ากลาง)] ไว้ดูว่ามีอะไร "เข้ามา" ไหม
        self.d_med = None
        self.arrival = False
        self.eyes_closed = False       # หลับ (ก้มหน้า): ไม่รับรู้ระยะ ไม่สนใจปุ่มอื่นนอกจาก "5"
        self.scanning = False          # สมองกำลังหมุนฐานกวาดหาคน (active sensing)
        self._fresh_view = False
        self.ignored_presses = []      # (เวลา, ปุ่ม) ที่ไม่สนใจเพราะหลับอยู่
        self.fake_wet_until = -1e9     # จำลองจุ่มน้ำ (จากเว็บ) ถึงเวลานี้
        self._alarm = (0.0, -1e9)      # สัญญาณตกใจจากการเข้ามาเร็ว (ระดับ, เวลา)
        self._self_move_until = -1e9
        self.self_moving = False
        self.blind_motion = False
        self.bg = {}                   # {(aim_bin, yaw_bin): ระยะฉากหลังที่จำไว้}
        self.bg_stat = {}              # {(aim_bin, yaw_bin): [ค่าเฉลี่ย, ความแปรปรวน, นิ่งตั้งแต่]}
        self.protect_target = False    # สมองบอก: กำลังผูกพันกับคนอยู่ ห้ามจำคนเป็นฉากหลัง
        self._bg_key = (0, 0)
        self.novel = True              # ระยะตอนนี้ใกล้กว่าฉากหลังชัดๆ (อาจเป็นคน)
        self._present_state = False    # มีคนไหม (จำข้ามเฟรมที่อ่านค่าไม่ได้)
        self.hab_caution = 1.0         # 1 = ยังตื่นตัวเต็มที่, 0 = ชินแล้ว
        self.hab_interest = 1.0

    # -------------------------------------------------------------- อินพุต
    def update(self, tlm, now):
        """tlm = dict จาก link.decode_telemetry (+ คีย์ 't_rx' ถ้ามี) ; None = ไม่มีข้อมูลใหม่"""
        c = self.cfg
        if tlm is not None:
            self._t_rx = tlm.get("t_rx", now)
            self.wet = tlm.get("wet")
            self._ingest_key(tlm.get("key"), tlm.get("key_seq"), now)
            self._update_self_motion(tlm.get("joints"), now)
            js = tlm.get("joints")
            if js and len(js) >= 4:                    # ทิศที่หัวมองตอนนี้ (มุมจริงจาก feedback)
                yaw, aim = js[0][0], js[1][0] + js[2][0] - js[3][0]
                self._bg_key = (int(round(aim / c.bg_aim_bin)), int(round(yaw / c.bg_yaw_bin)))
            d = tlm.get("dist_m")
            if d is None:
                self._last_n = []
                self.d_med = None
            else:
                self._last_n = (self._last_n + [d])[-c.med_n:]
                self.d_med = sorted(self._last_n)[len(self._last_n) // 2]
            # ความเร็วคิดจากค่ากลาง: ลำแสงข้ามขอบตัวคน (ตอนส่ายมองตาม) ทำให้ค่าดิบกระโดด ไม่ใช่คนพุ่ง
            dm = self.d_med
            if dm is not None and self._last_d is not None and self._last_dt_t is not None:
                dt = (now - self._last_dt_t) * self.speed
                if dt > 1e-3:
                    v_now = (dm - self._last_d) / dt
                    if abs(v_now) > c.jump_mps:          # กระโดด = คนละเป้าหมาย ไม่ใช่การเคลื่อนที่
                        self.vel = 0.0
                    else:
                        k = min(1.0, dt / c.vel_tau_s)
                        self.vel += k * (v_now - self.vel)
            if dm is None or self.self_moving or self.scanning:   # ระยะเปลี่ยนเพราะตัวเองขยับ ไม่ใช่ความเร็วของคน
                self.vel = 0.0
            self._last_d, self._last_dt_t = dm, now
            self.dist = d
            self._update_arrival(now)
            self._update_habituation(self.d_med, now)
            self._update_background(now)
            if not self.blind_motion:
                self._history.append((now, (self._d_ref, self._static_since, d)))
                while self._history and now - self._history[0][0] > 1.0 / self.speed:
                    self._history.pop(0)
        fresh = self._t_rx is not None and (now - self._t_rx) * self.speed <= c.tlm_stale_s
        if not fresh:
            self.dist, self.wet = None, None
        valid = fresh and self.dist is not None
        p = Percept(t=now, valid=valid)
        if valid:
            self._last_valid = now
            if self.eyes_closed:
                present = False                             # หลับอยู่: ไม่รับรู้ว่ามีใคร
                self._raw_since = None
            elif self.blind_motion:
                # ระหว่างขยับตัวเอง ระยะที่เห็นเป็นผลจากหัวกวาด -> ค้าง "มีคน/ไม่มีคน" ไว้ตามเดิม
                # (บั๊กจริง: เข้าท่า Sleep หัวกวาดเห็นของที่ 0.83 m -> นึกว่ามีคน -> ตื่นทันที)
                # หัวหันไปทางอื่น (สมองบอก) = มองไม่เห็นเป้าหมายเดิมจริงๆ -> ไม่นับว่ามีคน
                present = False if getattr(self, "_move_aim_changed", False) else self.percept.present
                self._raw_since = None                      # ต้องยืนยันใหม่หลังขยับเสร็จ
            else:
                # ฉากหลังที่คุ้นเคย (ผนัง/ของประจำที่) และสิ่งที่ชินแล้ว ไม่ใช่คน
                raw = self.present_h.update(-self.dist) and self.hab_interest > 0.0 and self.novel
                if not raw:
                    self._raw_since = None
                    present = False
                elif self._present_state:
                    present = True                          # มีอยู่แล้ว ไม่ต้องยืนยันซ้ำ
                else:
                    # คนเพิ่งโผล่: ต้องเห็นต่อเนื่อง present_confirm_s (ระยะมาก่อน feedback ข้อต่อ
                    # ถ้าเป็นหัวกวาดเอง จะถูกจับได้ก่อนครบเวลา แล้วยกเลิก)
                    self._raw_since = self._raw_since if self._raw_since is not None else now
                    present = (now - self._raw_since) * self.speed >= c.present_confirm_s
            p.in_beam = present                             # ลำแสงโดนคนอยู่ตอนนี้ (ตัวมองตามใช้)
            if present:
                self._last_in_beam = now
            elif (self._present_state and not self.eyes_closed and not self.blind_motion
                  and (now - self._last_in_beam) * self.speed < c.present_hold_s):
                present = True                              # เพิ่งหลุดขอบ ยังนับว่ามีคน (กำลังส่ายตาม)
            p.present = present
            self._present_state = present               # จำไว้ข้ามเฟรมที่อ่านค่าไม่ได้ (บั๊กเดิม: หายแวบเดียวต้องยืนยันใหม่)
            p.p = clamp((c.zone_far_m - self.dist) / (c.zone_far_m - c.too_close_m), 0.0, 1.0)
            p.zone = ("near" if self.dist < c.too_close_m else "mid" if self.dist < c.zone_far_m
                      else "far")
            p.closing = -self.vel
            dm = self.d_med if self.d_med is not None else self.dist
            p.rushing = ((-self.vel > c.rush_mps) and dm < c.loom_m          # looming: เร็ว + ใกล้ตัว
                         and not self.self_moving and not self.scanning and not self.eyes_closed)
            if present:
                self._present_since = self._present_since or now
                self._absent_since = None
            else:
                self._present_since = None
                self._absent_since = self._absent_since or now
            p.dwell = (now - self._present_since) * self.speed if self._present_since else 0.0
            p.quiet_time = (now - self._absent_since) * self.speed if self._absent_since else 0.0
            calm = abs(self.vel) < c.calm_mps
            p.facing = present and self.dist < c.engage_m and calm
        p.blind_time = 0.0 if valid else (now - self._last_valid) * self.speed
        self.percept = p
        return p

    def _update_self_motion(self, joints, now):
        """corollary discharge: โคมกำลังขยับตัวเองไหม (จากมุมข้อต่อใน telemetry)
        บอร์ดอ่านข้อต่อทีละตัววนกัน มุมจึงอัปเดตเป็นจังหวะ -> คิดความเร็วเฉลี่ยช่วง >= joint_window_s
        ระหว่างสมองสั่งกวาดหาคน ไม่นับ (สมองรู้อยู่แล้ว และต้องการให้มองเห็นระหว่างกวาด)"""
        c = self.cfg
        if not joints:
            self._refresh_self_moving(now)      # ไม่มีข้อมูลข้อต่อ (ซิม) -> ใช้แค่ efference copy
            return
        angles = [j[0] for j in joints[:4]]    # yaw shoulder elbow head_pitch ; roll หมุนรอบแกนลำแสง ไม่เปลี่ยนทิศที่มอง
        self._joint_hist.append((now, angles))
        while len(self._joint_hist) > 2 and (now - self._joint_hist[1][0]) * self.speed >= c.joint_window_s:
            self._joint_hist.pop(0)
        t0, a0 = self._joint_hist[0]
        span = (now - t0) * self.speed
        if span >= c.joint_window_s and not self.scanning:
            fastest = max(abs(a - b) for a, b in zip(angles, a0)) / span
            if fastest > c.self_move_dps:
                self._self_move_until = now + c.self_settle_s / self.speed
        self._refresh_self_moving(now)

    def simulate_wet(self, now, seconds=12.0):
        """จำลองจุ่มเซนเซอร์ความชื้นลงน้ำ (ไม่ต้องใช้น้ำจริง) -- ป่วยเหมือนจุ่มจริง"""
        self.fake_wet_until = now + seconds / self.speed

    def set_eyes(self, closed, now):
        """สมองสั่ง "หลับตา/ลืมตา" -- หลับ = ไม่รับรู้ระยะ ; ลืมตา (แอบดู/ตื่น) = มองใหม่ ไม่ถือเป็นฉากหลัง"""
        if closed == self.eyes_closed:
            return
        self.eyes_closed = closed
        if not closed:
            self._fresh_view = True
            self._d_ref, self._static_since = None, now
            self._recent, self._raw_since = [], None

    def on_self_motion(self, now, seconds, aim_changed=True):
        """efference copy: สมองบอกตรงๆ ว่ากำลังสั่งเปลี่ยนท่า (รู้ก่อนข้อต่อขยับ ไม่ต้องเดาจากความเร็ว)
        จำเป็นกับท่าที่ขยับช้า เช่น Sleep ที่ทรุดตัวช้ากว่าเกณฑ์ self_move_dps
        aim_changed=False = ท่าใหม่หัวชี้ทิศเดิม (ล็อกสายตา) -> สิ่งที่เห็นหลังขยับยังเป็นเป้าหมายเดิม"""
        self._self_move_until = max(self._self_move_until, now + seconds / self.speed)
        self._move_keeps_target = not aim_changed
        self._move_aim_changed = aim_changed
        self._refresh_self_moving(now)

    def _refresh_self_moving(self, now):
        c = self.cfg
        moving = now < self._self_move_until
        if moving and not self.self_moving:     # เริ่มขยับ: จำสิ่งที่เห็น "ก่อน" ขยับไว้
            # feedback ข้อต่อมาช้ากว่าระยะ -> ย้อนไป pre_move_s ก่อนตรวจพบ (ระยะอาจเพี้ยนไปก่อนแล้ว)
            self._pre_move = self._history[0][1] if self._history else None
            for t_h, snap in self._history:
                if now - t_h <= c.pre_move_s / self.speed:
                    break
                self._pre_move = snap
        if self.self_moving and not moving:
            if not getattr(self, "_move_keeps_target", False):
                self._move_ended = True         # ขยับเสร็จ (มุมมองเปลี่ยน): ตัดสินในรอบอ่านระยะถัดไป
            self._move_aim_changed = False
            self._move_keeps_target = False
        self.self_moving = moving
        # ระยะที่อ่านได้ระหว่างขยับเชื่อไม่ได้ เว้นแต่สมองบอกว่าหัวยังชี้ทิศเดิม (ล็อกสายตา)
        self.blind_motion = moving and not getattr(self, "_move_keeps_target", False)

    def _update_background(self, now):
        """ความคุ้นเคยกับสถานที่: เทียบระยะตอนนี้กับฉากหลังที่จำไว้ของทิศนี้"""
        c = self.cfg
        dm = self.d_med
        if dm is None or self.eyes_closed or self.blind_motion:
            return
        # ทิศที่ยังไม่เคยเห็น = ถือว่าว่าง (ฉากหลังไกล) -> ของใกล้ๆ น่าสนใจก่อน แล้วถ้านิ่งค่อยจำเป็นฉากหลัง
        # (ไม่ใช้ "ภาพแรก = ฉากหลัง" เพราะตอนเปิดโคม คนมักยืนอยู่หน้าโคมพอดี)
        b = self.bg.get(self._bg_key, c.bg_unknown_m)
        margin = max(c.bg_margin_m, c.bg_margin_rel * b)
        self.novel = dm < b - margin
        dt = 1.0 / 20.0                          # telemetry ~20 Hz
        # สิ่งของนิ่งสนิทเมื่อมองจากทิศเดิม ; คนไม่เคยนิ่งสนิท (หายใจ ขยับตัว)
        st = self.bg_stat.get(self._bg_key)
        if st is None:
            st = [dm, 0.0, now]
        a = min(1.0, dt * self.speed / c.bg_stat_tau_s)
        diff = dm - st[0]
        st[0] += a * diff
        st[1] = (1.0 - a) * (st[1] + a * diff * diff)
        if st[1] ** 0.5 > c.bg_still_std_m:
            st[2] = now
        self.bg_stat[self._bg_key] = st
        still = (now - st[2]) * self.speed >= c.bg_still_s and not self.protect_target
        if dm > b:                               # เห็นไกลกว่าที่จำ -> ฉากหลังอยู่ไกลกว่านั้น
            b += (dm - b) * c.bg_learn_far
        elif still:                              # นิ่งสนิทแบบสิ่งของ -> จำเป็นฉากหลัง (แม้ตอนนี้นับว่ามีคน)
            b += (dm - b) * min(1.0, dt * self.speed / c.bg_learn_still_s)
        elif not self._present_state:            # ของวางใหม่ ค่อยๆ จำ (มีคนอยู่ห้ามจำ ไม่งั้นคนกลายเป็นฉากหลัง)
            b += (dm - b) * min(1.0, dt * self.speed / c.bg_learn_near_s)
        self.bg[self._bg_key] = b

    def _update_arrival(self, now):
        """มีอะไร "เข้ามา" ใกล้จริงไหม: ระยะค่ากลางลดลง >= arrival_m ภายใน arrival_s
        (ตอนขยับตัวเองแบบมุมมองเปลี่ยน ไม่นับ -- ล้างประวัติทิ้ง)"""
        c = self.cfg
        if self.d_med is None or self.self_moving or self.scanning:
            # โคมขยับเอง (รวมโน้มเข้าหาแบบหัวชี้ทิศเดิม และกวาดหาคน): ระยะลดเพราะตัวเองเคลื่อนเข้าไป
            # ไม่ใช่ของ "เข้ามา" (บั๊กจริง: Curious โน้มเข้าหามือคน -> นึกว่ามือพุ่งเข้ามา -> กลัว)
            self._recent = []
            self.arrival = False
            return
        self._recent.append((now, self.d_med))
        while self._recent and (now - self._recent[0][0]) * self.speed > c.arrival_s:
            self._recent.pop(0)
        far = max(v for _, v in self._recent)
        self.arrival = far - self.d_med >= c.arrival_m

    def _update_habituation(self, d, now):
        c = self.cfg
        if d is None:
            return
        if self.blind_motion:
            self._d_ref = d                     # ระหว่างขยับตัวเอง: ฉากหลังเปลี่ยนตามหัว ไม่นับ
            self._static_since = now - 1e6
            self.hab_caution = 0.0              # ระยะที่เปลี่ยนเพราะตัวเอง ไม่ใช่เรื่องน่ากลัว (ความสนใจคงเดิม)
            return
        if getattr(self, "_move_ended", False) and self._fresh_view:
            self._move_ended = False            # เพิ่งลืมตา (แอบดู/ตื่น): สิ่งที่เห็นคือภาพใหม่ ไม่ใช่ฉากหลัง
            self._fresh_view = False
            self._d_ref, self._static_since = d, now
        elif getattr(self, "_move_ended", False):
            self._move_ended = False
            pre = getattr(self, "_pre_move", None)
            if pre is not None and pre[2] is not None and abs(d - pre[2]) < c.same_target_m:
                # ระยะใกล้เคียงก่อนขยับ = ยังเป็นเป้าหมายเดิม (เช่น คนที่ยืนอยู่) -> ต่อจากเดิม ไม่ใช่ฉากหลัง
                self._d_ref = pre[0] if pre[0] is not None else d
                self._static_since = pre[1]
            else:
                self._d_ref = d                 # หันไปเจอของใหม่เพราะตัวเองขยับ = ฉากหลังทันที
                self._static_since = now - 1e6
        else:
            # นิ่งไหม: ดูช่วงแกว่ง (สูงสุด-ต่ำสุด) ใน hab_win_s ไม่ใช่ระยะจากจุดอ้างอิงจุดเดียว
            # (บั๊ก: จุดอ้างอิงตกกลางการโยกตัว +-4 ซม. -> ไม่เกินเกณฑ์ 5 ซม. -> คนจริงกลายเป็นฉากหลัง)
            self._hab_win.append((now, d))
            while self._hab_win and (now - self._hab_win[0][0]) * self.speed > c.hab_win_s:
                self._hab_win.pop(0)
            vals = [v for _, v in self._hab_win]
            ref = self._d_ref if self._d_ref is not None else d
            tol = min(c.hab_tol_max, max(c.hab_tol_m, c.hab_tol_rel * ref))
            if self._d_ref is None or abs(d - self._d_ref) > tol or max(vals) - min(vals) > tol:
                self._d_ref = d                 # มีอะไรเปลี่ยน -> ตื่นตัวใหม่
                self._static_since = now
                self._hab_win = [(now, d)]
        still = (now - self._static_since) * self.speed
        self.hab_caution = 1.0 - clamp((still - c.hab_caution[0]) / c.hab_caution[1], 0.0, 1.0)
        self.hab_interest = 1.0 - clamp((still - c.hab_interest[0]) / c.hab_interest[1], 0.0, 1.0)

    def _ingest_key(self, key, seq, now):
        if seq is None:
            return
        if self._key_seq is None:            # เฟรมแรก: จำ seq ไว้ ไม่นับปุ่มเก่าที่กดก่อนเชื่อมต่อ
            self._key_seq = seq
            return
        if seq == self._key_seq or key is None:
            return
        self._key_seq = seq
        self.press(key, now)

    def press(self, key, now):
        """กดปุ่ม (จาก keypad จริง หรือจากคีย์บอร์ดตอนทดสอบ) ; หลับอยู่รับแค่ "5" (ปลุก)"""
        if self.eyes_closed and key != "5":
            self.ignored_presses = (self.ignored_presses + [(now, key)])[-20:]
            return
        self.presses.append((now, key))
        self.presses = self.presses[-20:]
        stim = KEY_STIMULI.get(key)
        if stim:
            self.pulses.append((now + self.cfg.key_pulse_s / self.speed, stim))
        if key in KEY_ONESHOT:
            self.pending_oneshot.append(KEY_ONESHOT[key])

    # -------------------------------------------------------------- สิ่งเร้า
    def stimuli(self, p):
        c = self.cfg
        S = {h: None for h in HORMONES}
        S["care"] = 0.0
        if p.valid and self.eyes_closed:              # หลับ: ระยะไม่มีผล นอกจาก "ไม่มีใคร" ทำให้ง่วงต่อ
            S["curiosity"] = S["caution"] = S["affinity"] = 0.0
            S["sleepiness"] = 0.5 if p.quiet_time >= c.absent_sleepy_s else 0.0
        elif p.valid:
            d = self.dist
            # เข้ามาในระยะ = อยากรู้พื้นฐาน แล้วยิ่งใกล้ยิ่งมาก (ระยะ 70 ซม. แคบ ถ้าคิดตามสัดส่วนล้วน ขอบนอกจะไม่สนใจเลย)
            closeness = c.curiosity_base + (1.0 - c.curiosity_base) * p.p
            S["curiosity"] = (c.curiosity_gain * closeness * self.hab_interest
                              if c.too_close_m <= d < c.zone_far_m else 0.0)
            dm = self.d_med if self.d_med is not None else d
            # ประชิด = ต้อง "เข้ามา" จริง (ไม่ใช่โต๊ะ/ตัวเองที่อยู่ใกล้อยู่แล้ว) และยังไม่ชิน
            caution = self.hab_caution if (dm < c.too_close_m and self.arrival) else 0.0
            if p.rushing:
                caution = max(caution, clamp(-self.vel / 1.5, 0.0, 1.0))
            # ยิ่งเข้ามาเร็ว อะดรีนาลีนยิ่งขึ้น (ผู้ใช้: เข้ามาเร็วๆ แล้วไม่ค่อยกลัว) -- ไม่นับตอนโคมขยับเอง/กวาดหา
            closing = -self.vel
            if (closing > c.fear_speed_lo and dm < c.zone_far_m
                    and not self.self_moving and not self.scanning):
                a = clamp((closing - c.fear_speed_lo) / (c.fear_speed_hi - c.fear_speed_lo), 0.0, 1.0)
                if a > self._alarm_level(p.t):
                    self._alarm = (a, p.t)              # เข้ามาเร็วแป๊บเดียว แต่ "ใจยังเต้นแรง" อีกสักพัก
            caution = max(caution, self._alarm_level(p.t))
            S["caution"] = caution
            # อยู่ด้วยกันนิ่งๆ นานเกิน affinity_full_s -> "อิ่ม" สิ่งเร้าค่อยๆ หมด ความผูกพันจึงลดลงเองได้
            # (ลูบหัว/ลูบตัวยังเติมได้เสมอ)
            fill = 1.0 - clamp((p.dwell - c.affinity_full_s) / c.affinity_fade_s, 0.0, 1.0)
            S["affinity"] = 0.5 * fill if (p.facing and p.dwell >= c.affinity_after_s) else 0.0
            S["sleepiness"] = 0.5 if (not p.present and p.quiet_time >= c.absent_sleepy_s) else 0.0
        if self._t_rx is not None and self.wet is not None:
            S["sickness"] = clamp(self.wet, 0.0, 1.0)
        if p.t < self.fake_wet_until:                  # ปุ่ม "จำลองจุ่มน้ำ" บนเว็บ
            S["sickness"] = 1.0
        now = p.t
        self.pulses = [(end, st) for end, st in self.pulses if end > now]
        for _, st in self.pulses:                 # ปุ่มทำงานแม้ระยะจะไม่รู้ (คนกดอยู่จริง)
            for h, v in st.items():
                S[h] = max(S[h] or 0.0, v)
        return S

    def _alarm_level(self, now):
        a, t0 = self._alarm
        left = 1.0 - (now - t0) * self.speed / self.cfg.alarm_hold_s
        return a * left if left > 0.0 else 0.0

    def after_hormones(self, bank):
        """ผลครั้งเดียวของบางปุ่ม (ปลุก, ดุ) ต่อฮอร์โมนที่สะสมอยู่"""
        for fx in self.pending_oneshot:
            for h, k in fx.items():
                if h in bank.hormones:
                    bank.hormones[h].h *= k
        self.pending_oneshot = []
