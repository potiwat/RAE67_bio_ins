"""ลูปหลักของโคม (fast loop) -- ไม่ขึ้นกับฮาร์ดแวร์ จึงทดสอบบน CPython ได้

ลำดับต่อรอบ
  1. อ่านเฟรมจากโน้ตบุ๊ก (ถ้ามี)  -> คำสั่งล่าสุดที่ seq ใหม่กว่า
  2. อ่านค่ากลับจากเซอร์โว 1 ตัว (วนไปเรื่อยๆ)
  3. ตัดสินโหมดจริง: E-stop > โดนขวาง/ร้อน > แพ็กเก็ตเก่า > โหมดจากโน้ตบุ๊ก
  4. motion -> safety -> sync write ไปทั้งบัสในแพ็กเก็ตเดียว
  5. ไฟ + telemetry
"""
import math
import time

import config as cfg
import link
from joints import JOINT_LIST, JOINT_BY_NAME, NAMES
from motion import MotionEngine
from safety import ActuatorSafety, Watchdog

try:                                    # MicroPython มี ticks_us ; CPython (เทส) ใช้ perf_counter แทน
    _us, _udiff = time.ticks_us, time.ticks_diff
except AttributeError:
    def _us():
        return int(time.perf_counter() * 1e6)

    def _udiff(a, b):
        return a - b

PROF_KEYS = ("feedback", "decide", "motion", "safety", "write", "light")

FAULT_BITS = {"estop": 1, "blocked": 2, "hot": 4, "fb_lost": 8,
              "undervolt": 16, "host_lost": 32, "bus_error": 64}


class Robot:
    def __init__(self, bus, light=None, estop=None, now=0.0, log=None):
        self.bus, self.light, self.estop_pin = bus, light, estop
        self._light_dt = 1.0
        self.prof = {k: 0 for k in PROF_KEYS}      # เวลารวม (us) ต่อขั้นใน step ไว้หาว่าช้าตรงไหน
        self.safety = ActuatorSafety()
        self.motion = None
        self.reader = link.Reader()
        self.watchdog = Watchdog(("loop", "bus"), 0.5, now)
        self.cmd = None
        self.cmd_time = -1e9
        self.cmd_seq = -1
        self.frames_ok = 0          # เฟรมที่ decode ผ่าน (ไว้ไล่ปัญหาลิงก์)
        self.mode = "Blind"
        self.fault = 0
        self.fb_i = 0
        self.tlm_seq = 0
        self.next_fb = now
        self.next_tlm = now
        self.boot_until = now + cfg.BOOT_SETTLE_S
        self.protect_until = -1e9
        self.log = log or (lambda m: None)
        self.t0 = now

    # ------------------------------------------------------------ บูต
    def start(self, now):
        """เปิดแรงบิดและไล่จากมุมจริง (ห้ามกระโดดไปท่าตั้งต้น)"""
        angles = {}
        for j in JOINT_LIST:
            fb = self.bus.feedback(j.sid)
            if fb is None:
                self.log("servo id %d ไม่ตอบ -- เช็คสาย/ID/ไฟเลี้ยง" % j.sid)
                continue
            self.safety.on_feedback(j.name, fb, now)
            angles[j.name] = j.tick_to_deg(fb["tick"])
            self.bus.torque(j.sid, True)
        self.motion = MotionEngine(dict((n, angles.get(n, 0.0)) for n in NAMES))
        self.safety.mark_resync()
        for n in NAMES:
            self.safety.states[n].cmd = angles.get(n)
        return angles

    def stop(self):
        for j in JOINT_LIST:
            try:
                self.bus.torque(j.sid, False)
            except Exception:
                pass

    # ------------------------------------------------------------ ข้อมูลเข้า
    def ingest(self, data, now):
        for body in self.reader.feed(data):
            if len(body) < 24:
                continue
            try:
                c = link.decode_command(body)
            except Exception:
                continue
            self.frames_ok += 1
            # รับเมื่อ seq ใหม่กว่า หรือเมื่อเพิ่งเงียบไปนาน (โน้ตบุ๊กรีสตาร์ทแล้วนับ seq ใหม่
            # ถ้าไม่มีเงื่อนไขหลัง จะทิ้งแพ็กเก็ตของโปรแกรมใหม่ทิ้งตลอดไป)
            restarted = (now - self.cmd_time) > cfg.PACKET_STALE_S
            if restarted or _seq_newer(c["seq"], self.cmd_seq):
                self.cmd, self.cmd_seq, self.cmd_time = c, c["seq"], now

    def poll_feedback(self, now):
        """อ่านทีละตัววนไป: บัสไม่แน่น และข้อต่อหนึ่งเสียไม่ทำให้ลูปค้าง"""
        if now < self.next_fb:
            return
        self.next_fb = now + 1.0 / (cfg.FEEDBACK_HZ * len(JOINT_LIST))
        j = JOINT_LIST[self.fb_i % len(JOINT_LIST)]
        self.fb_i += 1
        fb = self.bus.feedback(j.sid)
        if fb is not None and cfg.TICK_MIN - 20 <= fb["tick"] <= cfg.TICK_MAX + 20:
            self.safety.on_feedback(j.name, fb, now)
            self.watchdog.kick("bus", now)

    # ------------------------------------------------------------ ตัดสินโหมด
    def _decide(self, now):
        """คืน (mode, params, gaze, freeze) ; ชั้นนี้สำคัญกว่าทุกอย่างที่โน้ตบุ๊กสั่ง"""
        f = self.safety.health(now)
        bits = 0
        for k in f:
            key = k.split(":")[0]
            bits |= FAULT_BITS.get(key, 0)

        if self.estop_pin is not None and self.estop_pin.value() == 0:
            self.fault = bits | FAULT_BITS["estop"]
            return "Protect", cfg.SAFE_PARAMS, None, True          # ค้างท่า ไม่ฝืน

        if self.safety.any_blocked():
            self.protect_until = now + cfg.PROTECT_HOLD_S
        if now < self.protect_until:
            self.fault = bits | FAULT_BITS["blocked"]
            return "Protect", cfg.SAFE_PARAMS, None, True

        stale = self.cmd is None or (now - self.cmd_time) > cfg.PACKET_STALE_S
        if stale:
            bits |= FAULT_BITS["host_lost"]
            self.fault = bits
            if self.cmd is not None and (now - self.cmd_time) > cfg.HOST_LOST_S:
                return "Sleep", cfg.SAFE_PARAMS, None, False       # เงียบนาน -> ค่อยๆ ลงท่าพัก
            return "Blind", cfg.SAFE_PARAMS, None, False

        self.fault = bits
        p = dict(self.cmd["params"])
        for k in cfg.SAFE_PARAMS:                                   # พารามิเตอร์ขาดหรือเพี้ยน -> ใช้ค่าปลอดภัย
            v = p.get(k)
            if v is None or v != v:
                p[k] = cfg.SAFE_PARAMS[k]
        mode = self.cmd["mode"]
        if mode not in ("Idle", "Curious", "Engage", "Fear", "Sleep", "Blind", "Peek", "Sick"):
            mode = "Blind"
        return mode, p, self.cmd["gaze"], False

    # ------------------------------------------------------------ หนึ่งรอบ
    def step(self, dt, now):
        if self.motion is None:
            return
        prof = self.prof
        t0 = _us()
        self.poll_feedback(now)
        t1 = _us()
        mode, P, gaze, freeze = self._decide(now)
        self.mode = mode
        t2 = _us()

        if now < self.boot_until:                                   # ตอนบูต: นิ่งไว้ก่อน ให้ค่ากลับมาครบ
            self.motion.set_from_measured(self.safety.measured_angles())
            targets = self.motion.hold(dt)
            freeze = True
        elif freeze:
            targets = self.motion.hold(dt)
        else:
            targets = self.motion.step(dt, mode, P, gaze)
        t3 = _us()

        for n in NAMES:
            self.safety.filter(n, targets.get(n), dt, now, freeze=freeze)
        # ความเร็วคิดจากเวลาจริงของรอบนี้ ไม่ใช่คาบที่ตั้งไว้ (ลูปช้ากว่าที่ตั้ง -> เซอร์โวไปถึงเร็วเกินแล้วหยุดรอ = กระตุก)
        period = dt if 0.005 < dt < 0.2 else 1.0 / cfg.FAST_HZ
        items = self.safety.tick_items(getattr(cfg, "SMOOTH_MODE", "off"), period)
        t4 = _us()
        try:
            self.bus.sync_write_positions(items)
        except Exception as e:
            self.fault |= FAULT_BITS["bus_error"]
            self.log("bus write failed: %s" % e)
        if freeze:
            self.motion.set_from_measured(self.safety.measured_angles())
        t5 = _us()

        if self.light is not None:                                   # ไฟเปลี่ยนช้า อัปเดต ~20 Hz พอ (ไม่ต้องทุกรอบ)
            self._light_dt += dt
            tlm_due = now >= self.next_tlm                           # รอบที่ส่ง telemetry -> เลื่อนไฟไปรอบหน้า (ไม่ให้งานหนักชนกัน)
            if self._light_dt >= 0.05 and not tlm_due:
                track = 0.0
                m = self.motion
                if mode in ("Curious", "Engage") and m is not None and m.last_gaze is not None and m.gaze_w > 0.5:
                    err = m.last_gaze[0] - m.shaped.get("yaw", 0.0)     # ยังหันไม่ถึงเท่าไร -> ไฟวิ่งเร็วขึ้น
                    track = max(0.05, min(1.0, abs(err) / 15.0)) * (1.0 if err >= 0 else -1.0)
                self.light.update(P["brightness"], P["warmth"], mode, now - self.t0, self._light_dt, track)
                self._light_dt = 0.0
        self.watchdog.kick("loop", now)
        t6 = _us()
        prof["feedback"] += _udiff(t1, t0)
        prof["decide"] += _udiff(t2, t1)
        prof["motion"] += _udiff(t3, t2)
        prof["safety"] += _udiff(t4, t3)
        prof["write"] += _udiff(t5, t4)
        prof["light"] += _udiff(t6, t5)

    def telemetry(self, now, sensors=None):
        """คืนเฟรม telemetry หรือ None ถ้ายังไม่ถึงเวลา ; sensors = Sensors.fields()"""
        if now < self.next_tlm:
            return None
        self.next_tlm = now + 1.0 / cfg.TELEMETRY_HZ
        self.tlm_seq += 1
        rows = []
        for n in NAMES:
            s = self.safety.states[n]
            rows.append((s.meas if s.meas is not None else 0.0, s.load, s.temp))
        while len(rows) < 5:                    # เฟรม telemetry คงที่ 5 ช่อง: ข้อต่อที่ยังไม่มีส่ง 0
            rows.append((0.0, 0, 0))
        rows = rows[:5]
        return link.encode_telemetry(self.tlm_seq, int((now - self.t0) * 1000),
                                     self.mode, self.fault, rows, sensors)


def _seq_newer(a, b):
    """เทียบ seq แบบวนรอบ 16 บิต"""
    return b < 0 or ((a - b) & 0xFFFF) < 0x8000
