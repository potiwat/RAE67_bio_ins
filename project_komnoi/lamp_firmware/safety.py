"""ชั้นความปลอดภัยของ actuator -- เป็นทางเดียวที่ tick จะไปถึงเซอร์โว (single writer)

ลำดับ: validate -> clamp -> slew-rate -> (ตรวจโหลด/อุณหภูมิ/ไฟ) -> บัส
ต้องทำงานได้แม้โน้ตบุ๊กพัง เพราะฉะนั้นห้ามเรียกอะไรที่รอฝั่งโน้ตบุ๊ก
"""
import math

from joints import JOINT_LIST, JOINT_BY_NAME, NAMES, clamp
import config as cfg


class JointState:
    """สุขภาพของข้อต่อหนึ่งตัว"""
    def __init__(self, joint):
        self.j = joint
        self.cmd = None            # องศาที่สั่งไปล่าสุด (หลัง clamp + slew)
        self.meas = None           # องศาจริงจากเซอร์โว ; None = ยังไม่รู้
        self.load = 0
        self.temp = 0
        self.volt = 0.0
        self.last_fb = -1e9        # เวลาที่อ่านค่ากลับสำเร็จครั้งล่าสุด
        self.over_n = 0
        self.blocked = False       # โดนขวาง/โดนจับ (ผ่าน debounce + hysteresis)
        self.hot = False
        self.resync = True         # True = รอบหน้าให้ไล่จากมุมจริง
        self.last_tick = None      # tick ที่สั่งรอบก่อน (โหมด SMOOTH_MODE="speed")

    def stale(self, now):
        return (now - self.last_fb) > cfg.FEEDBACK_TIMEOUT_S

    def on_feedback(self, fb, now):
        self.meas = self.j.tick_to_deg(fb["tick"])
        self.load = fb["load"]
        self.temp = fb["temp"]
        self.volt = fb["volt"]
        self.last_fb = now
        mag = abs(self.load)
        lim = self.j.load_limit
        if self.blocked:
            if mag < lim * cfg.LOAD_RELEASE:
                self.over_n += 1
                if self.over_n >= cfg.LOAD_HOLD_N:
                    self.blocked, self.over_n = False, 0
            else:
                self.over_n = 0
        else:
            if mag > lim:
                self.over_n += 1
                if self.over_n >= cfg.LOAD_HOLD_N:
                    self.blocked, self.over_n = True, 0
            else:
                self.over_n = 0
        if self.hot and self.temp < cfg.OVERHEAT_CLEAR_C:
            self.hot = False
        elif (not self.hot) and self.temp >= cfg.OVERHEAT_C:
            self.hot = True


class ActuatorSafety:
    def __init__(self):
        self.states = {}
        for j in JOINT_LIST:
            self.states[j.name] = JointState(j)
        self.faults = set()

    # ------------------------------------------------------------ ค่ากลับจากเซอร์โว
    def on_feedback(self, name, fb, now):
        self.states[name].on_feedback(fb, now)

    def measured_angles(self):
        out = {}
        for n in NAMES:
            out[n] = self.states[n].meas
        return out

    def any_blocked(self):
        for n in NAMES:
            if self.states[n].blocked:
                return True
        return False

    def health(self, now):
        """คืน set ของปัญหาที่เจอตอนนี้ (ว่าง = ปกติ)"""
        f = set()
        for n in NAMES:
            s = self.states[n]
            if s.stale(now):
                f.add("fb_lost:" + n)
            if s.blocked:
                f.add("blocked:" + n)
            if s.hot:
                f.add("hot:" + n)
            if s.volt and s.volt < cfg.VOLTAGE_MIN_V:
                f.add("undervolt")
        self.faults = f
        return f

    # ------------------------------------------------------------ คำสั่งออก
    def filter(self, name, target_deg, dt, now, freeze=False):
        """คืนองศาที่ปลอดภัยสำหรับข้อต่อนี้ ; freeze = ค้างท่า (ไม่ตัดไฟ)"""
        s = self.states[name]
        j = s.j
        base = s.cmd
        if base is None or s.resync:
            base = s.meas if s.meas is not None else (target_deg if target_deg is not None else 0.0)
            s.resync = False                                   # กลับมาหลัง timeout: ไล่จากมุมจริง
        if freeze or target_deg is None or not _finite(target_deg):
            target = s.meas if s.meas is not None else base    # คำสั่งเสีย -> ค้างท่า
        else:
            target = target_deg
        target = clamp(target, j.soft_min, j.soft_max)         # angle clamping
        rate = j.max_rate
        if s.blocked or s.hot:
            rate *= 0.25                                       # โดนขวางหรือร้อน: ขยับช้าลงมาก
        step = rate * dt
        d = target - base
        if d > step:
            d = step
        elif d < -step:
            d = -step
        s.cmd = base + d                                       # slew-rate limiting
        return s.cmd

    def mark_resync(self, name=None):
        for n in (NAMES if name is None else (name,)):
            self.states[n].resync = True

    def tick_items(self, mode="off", period_s=0.025):
        """คืน [(servo id, tick, goal_speed, goal_time_ms)] สำหรับ sync write

        mode "off"   : ความเร็วเพดานคงที่ -> เซอร์โวพุ่งไปถึงแล้วหยุดรอรอบถัดไป (กระตุกเป็นขั้นบันได)
        mode "speed" : ความเร็ว = ระยะที่ต้องไปรอบนี้ / คาบลูป x1.3 -> ไปถึงพอดีตอนเป้าถัดไปมา (ไม่หยุดกลางทาง)
        mode "time"  : บอกเซอร์โวให้ไปถึงในเวลา 1.5 x คาบลูป (ให้เซอร์โวคำนวณความเร็วเอง)
        ทุกโหมดไม่เกินเพดานความเร็วของข้อต่อ (ชั้นกันซ้ำของ slew-rate ในซอฟต์แวร์)"""
        items = []
        t_ms = int(period_s * 1500)
        for n in NAMES:
            s = self.states[n]
            if s.cmd is None:
                continue
            tick = s.j.deg_to_tick(s.cmd, clamp_soft=False)
            cap = s.j.goal_speed()
            last = s.last_tick
            s.last_tick = tick
            if mode == "speed" and last is not None:
                v = int(abs(tick - last) / period_s * 1.3) + 1
                items.append((s.j.sid, tick, max(20, min(cap, v)), 0))
            elif mode == "time":
                items.append((s.j.sid, tick, 0, t_ms))
            else:
                items.append((s.j.sid, tick, cap, 0))
        return items


def _finite(x):
    return x == x and x not in (float("inf"), float("-inf"))


class Watchdog:
    """ทุกโมดูลต้อง kick ตามเวลา ไม่งั้นเข้าโหมดปลอดภัย"""
    def __init__(self, modules, timeout, now):
        self.timeout = timeout
        self.last = {}
        for m in modules:
            self.last[m] = now

    def kick(self, module, now):
        self.last[module] = now

    def expired(self, now):
        out = []
        for m in self.last:
            if now - self.last[m] > self.timeout:
                out.append(m)
        return out
