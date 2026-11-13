"""ชุดทดสอบ firmware บน CPython (ไม่ต้องมีบอร์ด) : python3 test_fw.py
ใช้เซอร์โวจำลองที่พูดโปรโตคอล SCS จริง และนาฬิกาเสมือน"""
import math
import sys
import traceback

import config as cfg
import link
from joints import JOINT_LIST, JOINT_BY_NAME, NAMES
from motion import MotionEngine
from robot import Robot, FAULT_BITS
from scs import SCSBus, ADDR_PRESENT_POSITION


# ---------------------------------------------------------------- เซอร์โว + บัสจำลอง
class FakeUART:
    def __init__(self, servos, big_endian=True, drop=0.0):
        self.servos, self.be, self.drop = servos, big_endian, drop
        self.rx = b""
        self.n = 0
        self.writes = 0

    def _w(self, v):
        return bytes([(v >> 8) & 0xFF, v & 0xFF]) if self.be else bytes([v & 0xFF, (v >> 8) & 0xFF])

    def _r(self, a, b):
        return ((a << 8) | b) if self.be else ((b << 8) | a)

    def any(self):
        return len(self.rx)

    def read(self, n=None):
        if not self.rx:
            return None
        n = len(self.rx) if n is None else n
        d, self.rx = self.rx[:n], self.rx[n:]
        return d

    def flush(self):
        pass

    def write(self, pkt):
        self.writes += 1
        assert ((~sum(pkt[2:-1])) & 0xFF) == pkt[-1]
        sid, inst = pkt[2], pkt[4]
        self.n += 1
        if self.drop and self.n % int(1 / self.drop) == 0:
            return
        if inst == 0x83:
            addr, dlen = pkt[5], pkt[6]
            body = pkt[7:-1]
            for i in range(0, len(body), dlen + 1):
                ch = body[i:i + dlen + 1]
                s = self.servos.get(ch[0])
                if s is not None:
                    s["goal"] = self._r(ch[1], ch[2])
                    if not s.get("stuck"):
                        s["tick"] = s["goal"]          # เซอร์โวตามคำสั่งทันที (อุดมคติ)
            return
        s = self.servos.get(sid)
        if s is None or s.get("dead"):
            return
        if inst == 1:
            params = b""
        elif inst == 2:
            addr, n = pkt[5], pkt[6]
            mem = bytearray(80)
            mem[42:44] = self._w(s.get("goal", s["tick"]))
            mem[56:58] = self._w(s["tick"])
            mem[58:60] = self._w(0)
            mem[60:62] = self._w(_tosign(s.get("load", 0)))
            mem[62] = int(s.get("volt", 7.2) * 10)
            mem[63] = s.get("temp", 35)
            params = bytes(mem[addr:addr + n])
        elif inst == 3:
            addr = pkt[5]
            if addr == 40:
                s["torque"] = pkt[6]
            elif addr == 42:
                s["goal"] = self._r(pkt[6], pkt[7])
                if not s.get("stuck"):
                    s["tick"] = s["goal"]
            params = b""
        else:
            params = b""
        body = bytes([sid, len(params) + 2, 0]) + params
        self.rx += b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])


def _dist_outside(x, j):
    if x < j.soft_min:
        return j.soft_min - x
    if x > j.soft_max:
        return x - j.soft_max
    return 0.0


def _closer(now_deg, prev_deg, j):
    return _dist_outside(now_deg, j) <= _dist_outside(prev_deg, j) + 1e-6


def _tosign(v):
    return ((-v) | (1 << 10)) if v < 0 else v


class FakePin:
    def __init__(self, v=1):
        self.v = v

    def value(self, v=None):
        if v is None:
            return self.v
        self.v = v


def make(now=0.0, drop=0.0, estop=None):
    servos = {}
    for j in JOINT_LIST:
        servos[j.sid] = dict(tick=j.center_tick, load=0, temp=35, volt=7.2, torque=0)
    u = FakeUART(servos, big_endian=cfg.SCS_BIG_ENDIAN, drop=drop)
    bot = Robot(SCSBus(u, dir_pin=FakePin(0), big_endian=cfg.SCS_BIG_ENDIAN), estop=estop, now=now)
    bot.start(now)
    return bot, servos, u


DT = 1.0 / cfg.FAST_HZ


def run(bot, seconds, t0=0.0, feed=None, dt=DT):
    """เดินลูป ; feed(t) คืนไบต์จากโน้ตบุ๊ก (หรือ None)"""
    t = t0
    end = t0 + seconds
    while t < end:
        if feed:
            d = feed(t)
            if d:
                bot.ingest(d, t)
        bot.step(dt, t)
        bot.telemetry(t)
        t += dt
    return t


def cmd(seq, t, mode, **kw):
    P = dict(tempo=1.0, amp=1.0, lean=0.0, gaze_follow=0.8, brightness=0.8, warmth=1.0)
    P.update(dict((k, v) for k, v in kw.items() if k in P))
    return link.encode_command(seq, int(t * 1000), mode, P, kw.get("gaze"))


def host(mode="Engage", period=0.02, **kw):
    box = {"n": 0, "last": -1.0}

    def f(t):
        if t - box["last"] < period:
            return None
        box["last"] = t
        box["n"] += 1
        return cmd(box["n"], t, mode, **kw)
    return f


# ---------------------------------------------------------------- การทดสอบ
def test_boot_does_not_jump():
    """เปิดเครื่องตอนแขนอยู่ท่าแปลกๆ -> ต้องไม่กระโดดไปท่าตั้งต้น"""
    now = 0.0
    servos = {}
    for j in JOINT_LIST:
        servos[j.sid] = dict(tick=j.center_tick + 180, load=0, temp=35, volt=7.2)
    u = FakeUART(servos, big_endian=cfg.SCS_BIG_ENDIAN)
    bot = Robot(SCSBus(u, dir_pin=FakePin(0), big_endian=cfg.SCS_BIG_ENDIAN), now=now)
    bot.start(now)
    start = dict((j.sid, servos[j.sid]["tick"]) for j in JOINT_LIST)
    t = run(bot, 0.3, feed=host())
    for j in JOINT_LIST:
        moved = abs(servos[j.sid]["tick"] - start[j.sid])
        limit = j.max_rate * 0.3 * 3.41 + 5                # ขยับได้ไม่เกิน slew-rate ต่อให้เริ่มนอกช่วง
        assert moved < limit, (j.name, moved, limit)


def test_slew_and_clamp_hold_through_everything():
    """ไม่ว่าโน้ตบุ๊กจะส่งอะไรมา ต้องรักษา 3 ข้อ
    1. tick ที่ส่งจริงอยู่ในช่วงเชิงกล  2. ไม่เกิน slew-rate
    3. เข้าช่วง soft limit แล้วห้ามออก และถ้าบูตมานอกช่วง ต้องวิ่งเข้าหาช่วงอย่างเดียว"""
    bot, servos, u = make()
    prev = dict((n, bot.safety.states[n].cmd) for n in NAMES)
    inside = dict((n, False) for n in NAMES)
    t = cfg.BOOT_SETTLE_S
    h = host("Engage", gaze=(40.0, -20.0))
    while t < 30.0:
        d = h(t)
        if d:
            bot.ingest(d, t)
        if 10 < t < 12:
            bot.cmd["params"]["amp"] = 50.0       # โน้ตบุ๊กส่งค่าบ้าๆ
        if 15 < t < 16:
            bot.cmd["params"]["tempo"] = float("nan")
        bot.step(DT, t)
        for n in NAMES:
            j = JOINT_BY_NAME[n]
            c = bot.safety.states[n].cmd
            assert cfg.TICK_MIN <= servos[j.sid]["goal"] <= cfg.TICK_MAX, (n, t)
            assert abs(c - prev[n]) <= j.max_rate * DT + 1e-6, (n, c - prev[n], t)
            if j.soft_min <= c <= j.soft_max:
                inside[n] = True
            else:
                assert not inside[n], (n, c, t)            # เข้าช่วงแล้วห้ามหลุดออก
                assert _closer(c, prev[n], j), (n, c, prev[n])   # ยังนอกช่วง -> ต้องวิ่งเข้าหา
            prev[n] = c
        t += DT


def test_host_silence_goes_safe_then_rest():
    bot, servos, u = make()
    run(bot, 5.0, feed=host("Engage"))
    assert bot.mode == "Engage"
    t = run(bot, 1.0, t0=5.0)                      # เงียบ 1 วินาที
    assert bot.mode == "Blind" and (bot.fault & FAULT_BITS["host_lost"])
    run(bot, 4.0, t0=t)                            # เงียบต่อจนเกิน HOST_LOST_S
    assert bot.mode == "Sleep"


def test_old_packets_ignored():
    bot, servos, u = make()
    run(bot, 3.0, feed=host("Engage"))
    seq_before = bot.cmd_seq
    bot.ingest(cmd(seq_before - 5, 3.0, "Fear"), 3.0)     # แพ็กเก็ตมาสลับลำดับ
    assert bot.cmd["mode"] != "Fear" and bot.cmd_seq == seq_before
    bot.ingest(cmd(seq_before + 1, 3.0, "Fear"), 3.0)
    assert bot.cmd["mode"] == "Fear"


def test_host_restart_resyncs_seq():
    """โน้ตบุ๊กรีสตาร์ท -> seq กลับไปเริ่มที่ 1 ; ถ้าไม่รับ จะเงียบค้างตลอดไป"""
    bot, servos, u = make()
    run(bot, 3.0, feed=host("Engage"))
    assert bot.cmd_seq > 10
    t = run(bot, 1.0, t0=3.0)                        # โน้ตบุ๊กดับไปแป๊บหนึ่ง
    run(bot, 2.0, t0=t, feed=host("Engage"))         # เปิดใหม่ เริ่มนับ seq ที่ 1
    assert bot.mode == "Engage", (bot.mode, bot.cmd_seq)


def test_seq_wraparound():
    bot, servos, u = make()
    bot.ingest(cmd(65530, 1.0, "Engage"), 1.0)
    assert bot.cmd_seq == 65530
    bot.ingest(cmd(3, 1.1, "Fear"), 1.1)                  # วนรอบ 16 บิต -> ต้องถือว่าใหม่กว่า
    assert bot.cmd["mode"] == "Fear"


def test_corrupt_frames_never_reach_motors():
    bot, servos, u = make()
    run(bot, 3.0, feed=host("Engage"))
    before = dict((j.sid, servos[j.sid]["tick"]) for j in JOINT_LIST)
    junk = bytes(range(256)) * 4
    bot.ingest(junk, 3.0)
    bot.step(DT, 3.0)
    for j in JOINT_LIST:
        assert abs(servos[j.sid]["tick"] - before[j.sid]) < 20


def test_blocked_joint_enters_protect_and_holds():
    bot, servos, u = make()
    run(bot, 4.0, feed=host("Engage"))
    sid = JOINT_BY_NAME["shoulder"].sid
    servos[sid]["load"] = min(1000, JOINT_BY_NAME["shoulder"].load_limit + 50)   # มีมือไปจับแขนไว้
    servos[sid]["stuck"] = True
    t = run(bot, 1.5, t0=4.0, feed=host("Engage"))
    assert bot.mode == "Protect" and (bot.fault & FAULT_BITS["blocked"]), (bot.mode, bot.fault)
    held = servos[sid]["goal"]
    t = run(bot, 1.0, t0=t, feed=host("Engage"))
    assert abs(servos[sid]["goal"] - held) < 30      # ค้างท่า ไม่ฝืนดันต่อ
    assert servos[sid].get("torque") != 0            # ไม่ตัดไฟ (ไม่งั้นแขนตกใส่มือ)
    servos[sid]["load"] = 0
    servos[sid]["stuck"] = False
    t = run(bot, 3.0, t0=t, feed=host("Engage"))
    assert bot.mode == "Engage", bot.mode            # ปล่อยแล้วกลับมาทำงานต่อ


def test_overheat_slows_then_clears():
    bot, servos, u = make()
    run(bot, 3.0, feed=host("Engage"))
    sid = JOINT_BY_NAME["elbow"].sid
    servos[sid]["temp"] = 70
    t = run(bot, 1.0, t0=3.0, feed=host("Engage"))
    assert bot.fault & FAULT_BITS["hot"]
    servos[sid]["temp"] = 50
    run(bot, 1.0, t0=t, feed=host("Engage"))
    assert not (bot.fault & FAULT_BITS["hot"])


def test_dead_servo_does_not_stall_loop():
    bot, servos, u = make()
    servos[JOINT_BY_NAME[NAMES[-1]].sid]["dead"] = True     # สายหลุดกลางทาง
    t = run(bot, 3.0, feed=host("Engage"))
    assert bot.fault & FAULT_BITS["fb_lost"]
    assert bot.mode == "Engage"                               # ข้อต่ออื่นยังทำงาน
    assert bot.safety.states["yaw"].meas is not None


def test_noisy_bus_still_runs():
    bot, servos, u = make(drop=0.25)                          # 1 ใน 4 ของแพ็กเก็ตหาย
    run(bot, 6.0, feed=host("Engage"))
    assert bot.mode in ("Engage", "Protect", "Blind")
    assert bot.safety.states["shoulder"].meas is not None


def test_estop_holds_posture_without_cutting_torque():
    pin = FakePin(1)
    bot, servos, u = make(estop=pin)
    run(bot, 3.0, feed=host("Engage"))
    pin.value(0)
    t = run(bot, 0.5, t0=3.0, feed=host("Engage"))
    assert bot.mode == "Protect" and (bot.fault & FAULT_BITS["estop"])
    held = dict((j.sid, servos[j.sid]["goal"]) for j in JOINT_LIST)
    t = run(bot, 2.0, t0=t, feed=host("Engage"))
    for j in JOINT_LIST:
        assert abs(servos[j.sid]["goal"] - held[j.sid]) < 25
    pin.value(1)
    run(bot, 2.0, t0=t, feed=host("Engage"))
    assert bot.mode == "Engage"


def test_resync_after_loop_hiccup():
    """ลูปสะดุด 2 วินาที (GC/ไฟตก) แล้วมีคนดันแขนไป -> ต้องไล่จากมุมจริง ไม่กระโดด"""
    bot, servos, u = make()
    run(bot, 3.0, feed=host("Engage"))
    sid = JOINT_BY_NAME["shoulder"].sid
    servos[sid]["tick"] += 150                                 # ถูกดันระหว่างที่ลูปค้าง
    bot.safety.mark_resync()
    t, prev = 5.0, servos[sid]["tick"]
    for i in range(30):
        bot.ingest(cmd(1000 + i, t, "Engage"), t)
        bot.step(DT, t)
        assert abs(servos[sid]["tick"] - prev) <= JOINT_BY_NAME["shoulder"].max_rate * DT * 3.42 + 2
        prev = servos[sid]["tick"]
        t += DT


def test_telemetry_roundtrip():
    bot, servos, u = make()
    run(bot, 2.0, feed=host("Curious"))
    bot.next_tlm = 0.0
    fr = bot.telemetry(2.0)
    r = link.Reader()
    [body] = r.feed(fr)
    d = link.decode_telemetry(body)
    assert d["state"] == "Curious" and len(d["joints"]) == 5
    assert abs(d["joints"][0][0] - bot.safety.states["yaw"].meas) < 0.2


def test_tick_math_and_endianness_guard():
    j = JOINT_BY_NAME[NAMES[-1]]
    assert j.deg_to_tick(999) == j.deg_to_tick(j.soft_max)
    assert cfg.TICK_MIN <= j.deg_to_tick(-999) <= cfg.TICK_MAX
    mid = (j.soft_min + j.soft_max) / 2.0
    assert abs(j.tick_to_deg(j.deg_to_tick(mid)) - mid) < 0.3
    bot, servos, u = make()
    sid = JOINT_LIST[0].sid
    servos[sid]["tick"] = 900                                   # 0x0384 -> สลับไบต์แล้วหลุดช่วงชัดเจน
    bad = SCSBus(FakeUART(servos, big_endian=not cfg.SCS_BIG_ENDIAN),
                 dir_pin=FakePin(0), big_endian=cfg.SCS_BIG_ENDIAN)
    v = bad.read_word(sid, ADDR_PRESENT_POSITION)
    assert v is None or v > 1100, v
    good = SCSBus(FakeUART(servos, big_endian=cfg.SCS_BIG_ENDIAN),
                  dir_pin=FakePin(0), big_endian=cfg.SCS_BIG_ENDIAN)
    assert good.read_word(sid, ADDR_PRESENT_POSITION) == 900


def test_poses_settle_near_target_and_inside_limits():
    """ทุกโหมดต้องนิ่งใกล้ท่าที่ตั้งไว้ และอยู่ในช่วงข้อต่อจริงพร้อมเผื่อขอบ"""
    from motion import POSES
    for mode in POSES:
        m = MotionEngine(dict((n, 0.0) for n in NAMES))
        P = dict(tempo=1.0, amp=1.0, lean=0.0, gaze_follow=0.0, brightness=0.8, warmth=1.0)
        for _ in range(400):
            a = m.step(0.01, mode, P, None)
        for n in NAMES:
            j = JOINT_BY_NAME[n]
            if not (mode == "Fear" and n == "yaw"):        # Fear ตั้งใจหันหนีออกข้าง
                assert abs(a[n] - POSES[mode][n]) < 6.0, (mode, n, a[n], POSES[mode][n])
            assert j.soft_min <= a[n] <= j.soft_max, (mode, n, a[n])


def test_gaze_turns_base_toward_person():
    m = MotionEngine(dict((n, 0.0) for n in NAMES))
    P = dict(tempo=1.0, amp=1.0, lean=0.0, gaze_follow=1.0, brightness=0.8, warmth=1.0)
    for _ in range(400):
        a = m.step(0.01, "Engage", P, (25.0, 0.0))
    assert 18.0 < a["yaw"] < 32.0, a["yaw"]
    for _ in range(400):
        a = m.step(0.01, "Engage", P, (-25.0, 0.0))
    assert -32.0 < a["yaw"] < -18.0, a["yaw"]


# ---------------------------------------------------------------- เซนเซอร์ความชื้น
class _FakeADC:
    def __init__(self, seq, powered_ref):
        self.seq, self.powered = list(seq), powered_ref
    def read_u16(self):
        if not self.powered["on"]:
            return 0                                   # ไม่มีไฟ = อ่านได้ 0 (ต้องไม่เกิดถ้าเปิดไฟก่อนอ่าน)
        v = self.seq[0]
        if len(self.seq) > 1:
            self.seq.pop(0)
        if v is None:
            raise OSError("adc")
        return v


class _FakePin:
    def __init__(self, ref):
        self.ref, self.on_count = ref, 0
    def value(self, v):
        self.ref["on"] = bool(v)
        self.on_count += 1 if v else 0


def _moist(seq, dry=60000, wet=20000, period=1000):
    from moisture import Moisture
    ref = {"on": False}
    pin = _FakePin(ref)
    m = Moisture(_FakeADC(seq, ref), pin, dry, wet, period_ms=period,
                 sleep_ms=lambda ms: None, ticks_diff=lambda a, b: a - b)
    return m, pin, ref


def test_moisture_maps_dry_wet_and_powers_only_while_reading():
    m, pin, ref = _moist([60000] * 8 + [20000] * 8 + [40000] * 8)
    assert ref["on"] is False                          # เริ่มมาไฟต้องปิด
    m.poll(0)
    assert m.wet == 0.0 and ref["on"] is False         # แห้ง ; อ่านเสร็จปิดไฟ
    m.poll(1000)
    assert m.wet == 1.0 and ref["on"] is False         # จุ่มน้ำ
    m.poll(2000)
    assert abs(m.wet - 0.5) < 1e-6
    assert pin.on_count == 3                           # เปิดไฟแค่ตอนอ่านจริง


def test_moisture_respects_period_and_clamps():
    m, pin, ref = _moist([70000] * 8 + [5000] * 8)
    assert m.poll(0) is True and m.wet == 0.0          # แห้งกว่าที่คาลิเบรต -> 0 ไม่ติดลบ
    assert m.poll(500) is False and pin.on_count == 1  # ยังไม่ครบรอบ ไม่อ่าน ไม่เปิดไฟ
    assert m.poll(1000) is True and m.wet == 1.0       # เปียกกว่าที่คาลิเบรต -> 1


def test_moisture_read_error_gives_none_and_power_off():
    m, pin, ref = _moist([None])
    m.poll(0)
    assert m.wet is None and m.errors == 1 and ref["on"] is False


def test_moisture_reverse_polarity_module():
    m, _, _ = _moist([1000] * 8 + [30000] * 8, dry=1000, wet=30000)   # โมดูลที่เปียกแล้วค่าเพิ่ม
    m.poll(0)
    assert m.wet == 0.0
    m.poll(1000)
    assert m.wet == 1.0


# ---------------------------------------------------------------- อัลตร้าโซนิค
class _TrigPin:
    def __init__(self):
        self.v, self.pulses = 0, 0
    def value(self, v):
        if v and not self.v:
            self.pulses += 1
        self.v = v


def _us(echo_seq, **kw):
    from ultrasonic import Ultrasonic
    seq = list(echo_seq)
    def echo(timeout):
        v = seq.pop(0) if len(seq) > 1 else seq[0]
        if v == "err":
            raise OSError("timeout")
        return v
    trig = _TrigPin()
    u = Ultrasonic(trig, echo, sleep_us=lambda us: None, ticks_diff=lambda a, b: a - b, **kw)
    return u, trig


def _m_to_us(m):
    return int(m * 2 / 0.000343)


def test_ultrasonic_distance_and_filter_rejects_spike():
    u, trig = _us([_m_to_us(1.0)] * 3 + [_m_to_us(0.1)] + [_m_to_us(1.0)] * 3)
    t = 0
    for _ in range(3):
        u.poll(t); t += 60
    assert abs(u.dist - 1.0) < 0.01, u.dist
    u.poll(t); t += 60                                   # ค่าหลุดตัวเดียว (0.1 m)
    assert abs(u.raw_m - 0.1) < 0.01
    assert u.dist > 0.95, u.dist                         # median ตัดทิ้ง ไม่กระโดด
    assert trig.pulses == 4


def test_ultrasonic_period_and_invalid_values():
    u, trig = _us([-2, 0, "err", _m_to_us(5.0), _m_to_us(0.005)])
    assert u.poll(0) is True and u.raw_m is None         # timeout
    assert u.poll(30) is False and trig.pulses == 1      # ยังไม่ครบ 60 ms ไม่ยิงซ้ำ
    for t in (60, 120, 180, 240):
        u.poll(t)
        assert u.raw_m is None, (t, u.raw_m)             # 0 / error / ไกลเกิน 4 m / ใกล้เกิน
    assert u.dist is None and u.bad == 5


def test_ultrasonic_goes_unknown_when_stale():
    u, _ = _us([_m_to_us(0.8)] * 2 + [-2] * 20)
    t = 0
    for _ in range(2):
        u.poll(t); t += 60
    assert u.dist is not None
    while t < 400:                                       # พลาดสั้นๆ ยังจำค่าเดิม
        u.poll(t); t += 60
    assert u.dist is not None
    while t < 800:                                       # พลาดนานเกิน 500 ms -> ไม่รู้
        u.poll(t); t += 60
    assert u.dist is None


# ---------------------------------------------------------------- keypad 4x3
class _KPin:
    IN, OUT, PULL_UP = 1, 2, 3
    def __init__(self, idx, board):
        self.idx, self.board, self.mode, self.out = idx, board, self.IN, 1
    def init(self, mode, pull=None, value=None):
        self.mode = mode
        if value is not None:
            self.out = value
    def value(self, v=None):
        if v is not None:
            self.out = v
            return
        if self.mode == self.OUT:
            return self.out
        for a, b in self.board["pressed"]:                 # ปุ่มที่กด = เชื่อมสองขา
            other = b if a == self.idx else a if b == self.idx else None
            if other is not None:
                op = self.board["pins"][other]
                if op.mode == op.OUT and op.out == 0:
                    return 0
        return 1                                           # pull-up


def _kp(pairs=None, wiring=None):
    from keypad import Keypad
    board = {"pressed": []}
    pins = [_KPin(i, board) for i in range(7)]
    board["pins"] = pins
    k = Keypad(pins, pairs, period_ms=20, debounce_n=3, ticks_diff=lambda a, b: a - b)
    return k, board


def test_keypad_default_layout_and_debounce():
    from keypad import default_pairs
    k, board = _kp()
    board["pressed"] = [default_pairs()["5"]]
    got = [k.poll(t) for t in range(0, 100, 20)]
    assert got.count("5") == 1 and got[:2] == [None, None], got   # กันเด้ง 3 รอบ แล้วส่งครั้งเดียว
    assert k.held == "5"
    board["pressed"] = []
    for t in range(100, 200, 20):
        assert k.poll(t) is None
    assert k.held is None
    board["pressed"] = [default_pairs()["#"]]
    assert [k.poll(t) for t in range(200, 300, 20)].count("#") == 1


def test_keypad_bounce_is_ignored():
    from keypad import default_pairs
    k, board = _kp()
    seq = [default_pairs()["7"], None, default_pairs()["7"], None]   # เด้งไปมา ไม่นิ่ง 3 รอบ
    for t, pr in zip(range(0, 80, 20), seq):
        board["pressed"] = [pr] if pr else []
        assert k.poll(t) is None


def test_keypad_scrambled_wiring_with_learned_pairs():
    """สายแพลำดับแปลก (เช่น C2 R1 C1 R4 C3 R3 R2) -> ใช้ pairs ที่เรียนรู้แล้วต้องถอดถูกทุกปุ่ม"""
    from keypad import LAYOUT
    row_pin = {0: 1, 1: 6, 2: 5, 3: 3}
    col_pin = {0: 2, 1: 0, 2: 4}
    learned = {LAYOUT[r * 3 + c]: (row_pin[r], col_pin[c]) for r in range(4) for c in range(3)}
    k, board = _kp(pairs=learned)
    for key, pr in learned.items():
        board["pressed"] = [pr]
        assert k.scan() == key, (key, pr, k.scan())
    board["pressed"] = []
    assert k.scan() is None
    for p in board["pins"]:
        assert p.mode == p.IN                              # สแกนเสร็จต้องปล่อยทุกขาลอย ไม่ค้าง OUT


# ---------------------------------------------------------------- ไฟวงแหวน
def test_neopixel_ring_brightness_is_capped():
    from led import Light
    class NP(list):
        def write(self):
            self.writes = getattr(self, "writes", 0) + 1
    np = NP([(0, 0, 0)] * 12)
    light = Light(neopixel=np, n=12, max_b=0.3)
    for i in range(100):
        light.update(1.0, 1.0, "Engage", i * 0.1, 0.1)      # ขอสว่างเต็มที่ (สบายดี)
    assert max(max(px) for px in np) <= int(255 * 0.3), np[0]
    assert all(px == np[0] for px in np) and 1 <= np.writes < 100   # สีนิ่งแล้ว ไม่เขียนซ้ำ
    w = np.writes
    light.update(1.0, 1.0, "Engage", 99.0, 0.1)
    assert np.writes == w                                           # สีเดิม -> ไม่เขียนวงแหวนอีก (ประหยัดเวลาลูป)
    for i in range(100):
        light.update(0.0, 0.5, "Sleep", 10 + i * 0.1, 0.1)
    assert max(max(px) for px in np) <= 2                     # หรี่จนเกือบดับ
    light.update(0.8, 0.5, "Protect", 30.0, 0.1)              # โหมดมีปัญหา: amber ยังอยู่ใต้เพดาน
    assert max(max(px) for px in np) <= int(255 * 0.3)


# ---------------------------------------------------------------- telemetry + เซนเซอร์
def _tlm_body(frame_bytes):
    r = link.Reader()
    frames = r.feed(frame_bytes)
    assert len(frames) == 1
    return frames[0]


def test_telemetry_carries_sensors_and_unknowns():
    rows = [(1.5, 10, 30)] * 5
    d = link.decode_telemetry(_tlm_body(link.encode_telemetry(7, 1234, "Idle", 0, rows, (850, 42, ord("7"), 3))))
    assert d["dist_m"] == 0.85 and d["wet"] == 0.42 and d["key"] == "7" and d["key_seq"] == 3
    assert d["joints"][0] == (1.5, 10, 30) and d["seq"] == 7
    d = link.decode_telemetry(_tlm_body(link.encode_telemetry(8, 1, "Idle", 0, rows)))
    assert d["dist_m"] is None and d["wet"] is None and d["key"] is None   # ไม่มีเซนเซอร์ = ไม่รู้


def test_telemetry_old_frame_without_sensors_still_decodes():
    import struct
    flat = []
    for _ in range(5):
        flat += [15, 10, 30]
    body = struct.pack("<HIBH" + "hhB" * 5, 1, 2, 0, 0, *flat)
    d = link.decode_telemetry(body)
    assert d["dist_m"] is None and d["joints"][0] == (1.5, 10, 30)


class _EchoPin:
    IRQ_RISING, IRQ_FALLING = 1, 2
    def __init__(self):
        self.v, self.handler = 0, None
    def irq(self, handler=None, trigger=None):
        self.handler = handler
    def value(self):
        return self.v
    def edge(self, v):
        self.v = v
        self.handler(self)


def test_ultrasonic_irq_does_not_block_and_reads_previous_shot():
    from ultrasonic import UltrasonicIRQ
    clock = [0]
    echo = _EchoPin()
    u = UltrasonicIRQ(_TrigPin(), echo, ticks_us=lambda: clock[0], sleep_us=lambda us: None,
                      ticks_diff=lambda a, b: a - b, period_ms=60)
    u.poll(0)
    assert u.raw_m is None                                  # ยิงครั้งแรก ยังไม่มีผล
    clock[0] = 1000; echo.edge(1)                           # เสียงสะท้อนมาทีหลัง (interrupt)
    clock[0] = 1000 + 5831; echo.edge(0)                    # ~1.0 m
    u.poll(60)
    assert abs(u.raw_m - 1.0) < 0.01, u.raw_m
    u.poll(120)                                             # ยิงแล้วไม่มีเสียงสะท้อน
    assert u.raw_m is None and u.dist is not None           # พลาดครั้งเดียว ยังจำค่าเดิม


def test_sensor_hub_key_seq_and_fields():
    from sensors import Sensors, NO_DIST, NO_WET
    class K:
        def __init__(self, seq):
            self.seq = list(seq)
        def poll(self, now):
            return self.seq.pop(0) if self.seq else None
    hub = Sensors(None, None, K(["1", None, "1", "?", "9"]))
    assert hub.fields() == (NO_DIST, NO_WET, 0, 0)
    for t in range(5):
        hub.poll(t * 20)
    d, w, k, ks = hub.fields()
    assert chr(k) == "9" and ks == 3                        # กด 1 สองครั้งนับแยก ; "?" ไม่นับ
    class Boom:
        def poll(self, now):
            raise OSError("x")
    hub = Sensors(Boom(), Boom(), Boom())
    hub.poll(0)                                             # เซนเซอร์พังต้องไม่ทำให้ลูปหลักพัง
    assert hub.err == 3


# ---------------------------------------------------------------- ความนุ่มนวล (SMOOTH_MODE)
def test_tick_items_smooth_modes():
    from safety import ActuatorSafety
    from joints import NAMES, JOINT_BY_NAME
    saf = ActuatorSafety()
    st = saf.states[NAMES[0]]
    j = JOINT_BY_NAME[NAMES[0]]
    st.cmd = 0.0
    off = saf.tick_items("off", 0.025)[0]
    assert off[2] == j.goal_speed() and off[3] == 0                 # เดิม: เพดานคงที่
    saf.tick_items("speed", 0.025)                                  # รอบแรก: จำ tick ไว้
    st.cmd = 3.0                                                    # 3 องศา ใน 25 ms
    sp = saf.tick_items("speed", 0.025)[0]
    want = int(abs(j.deg_to_tick(3.0) - j.deg_to_tick(0.0)) / 0.025 * 1.3) + 1
    assert sp[2] == max(20, min(j.goal_speed(), want)), (sp, want)  # ไปถึงพอดีรอบถัดไป ไม่เกินเพดาน
    st.cmd = 3.0
    assert saf.tick_items("speed", 0.025)[0][2] == 20                # ไม่ขยับ -> ความเร็วขั้นต่ำ (ไม่ใช่ 0 = เร็วสุด)
    tm = saf.tick_items("time", 0.025)[0]
    assert tm[2] == 0 and tm[3] == 37                               # ไปถึงใน 1.5 x คาบ


def test_sync_write_carries_goal_time():
    from scs import SCSBus
    sent = []
    class U:
        def write(self, b):
            sent.append(bytes(b))
        def read(self, n=None):
            return None
        def any(self):
            return 0
    bus = SCSBus(U(), dir_pin=None, big_endian=True, baud=1000000)
    bus._tx = lambda body: sent.append(list(body))
    bus.sync_write_positions([(4, 500, 100, 37), (9, 510, 200)])
    body = sent[-1]
    assert body[5:12] == [4, 0x01, 0xF4, 0, 37, 0, 100], body[5:12]  # pos 500, time 37, speed 100
    assert body[12:19] == [9, 0x01, 0xFE, 0, 0, 0, 200]               # ไม่ระบุเวลา = 0 เหมือนเดิม


def test_light_emotion_colors_sick_tint_and_fault():
    from led import Light, EMOTION_RGB, SICK_RGB
    class NP(list):
        def write(self):
            pass
    def settle(mode, health, t0=0.0):
        np = NP([(0, 0, 0)] * 4)
        L = Light(neopixel=np, n=4, max_b=0.3)
        for i in range(60):
            rgb, b = L.update(1.0, health, mode, t0 + i * 0.1, 0.1)
        return rgb, b
    for mode, want in EMOTION_RGB.items():                       # สีตรงตาราง Lab 06
        rgb, _ = settle(mode, 1.0)
        assert all(abs(a - w) <= 2 for a, w in zip(rgb, want)), (mode, rgb, want)
    well, _ = settle("Fear", 1.0)
    sick, _ = settle("Fear", 0.0)
    assert abs(sick[0] - SICK_RGB[0]) < abs(well[0] - SICK_RGB[0])  # ป่วย -> ซีดไปทางเหลืองเขียว
    assert sick[1] > well[1] + 50                                 # แดงจัด -> มีเขียวปน
    rgb, b = settle("Blind", 1.0)
    assert rgb[0] == rgb[1] == rgb[2] and b <= 0.3                # ระบบมีปัญหา = ขาวหรี่ (ไม่ใช่อำพัน)


def test_engage_dance_is_short_burst():
    """ผู้ใช้: เต้นผูกพันนานไป -> เต้นแค่ ~4 วิแรกที่เข้า Engage แล้วหยุด"""
    from motion import MotionEngine, POSES, DANCE_S
    from joints import NAMES
    P = dict(tempo=1.0, amp=0.0, lean=0.0, gaze_follow=0.0, brightness=0.8, warmth=1.0)   # amp 0 = ไม่มีหายใจ
    m = MotionEngine({n: POSES["Idle"][n] for n in NAMES})
    dt, t, early, late = 0.025, 0.0, [], []
    while t < 9.0:
        out = m.step(dt, "Engage", P, None)
        x1, x2 = m._advance_cpg(0.0, 1.0)
        tgt = m._compose("Engage", P, None, 0.0, 0.0, 0.0)
        dev = abs(tgt["head_roll"] - POSES["Engage"]["head_roll"])
        (early if 1.0 < t < 2.5 else late if t > DANCE_S + 0.5 else []).append(dev)
        t += dt
    assert max(early) > 4.0, max(early)                       # เต้นจริงช่วงแรก
    assert max(late) < 0.5, max(late)                          # หยุดแล้ว


def test_curious_leans_in_smoothly_but_yaw_stays_quick():
    """ผู้ใช้: สนใจพุ่งแรงเกิน -> แขนโน้มเข้าหานุ่มๆ ไม่เด้งเลยเป้า ; แต่ฐานหมุนมองตามต้องยังไว"""
    from motion import MotionEngine, POSES
    from joints import NAMES
    P = dict(tempo=1.0, amp=0.0, lean=0.0, gaze_follow=1.0, brightness=0.8, warmth=1.0)
    m = MotionEngine({n: POSES["Idle"][n] for n in NAMES})
    for _ in range(60):
        m.step(1 / 30, "Idle", P, None)
    dt, prev, vmax, peak = 1 / 30, m.shaped["shoulder"], 0.0, -1e9
    goal = POSES["Curious"]["shoulder"]
    for i in range(150):                                       # 5 วิ
        m.step(dt, "Curious", P, None if i < 90 else (40.0, 0.0))
        sh = m.shaped["shoulder"]
        vmax = max(vmax, abs(sh - prev) / dt)
        peak = max(peak, sh)
        prev = sh
        if i == 89:
            yaw0 = m.shaped["yaw"]
    assert vmax < 150.0, vmax                                  # วัดแล้ว: เดิม 449 องศา/วิ เด้งเลย 10 ; ใหม่ 127 ไม่เด้ง
    assert peak < goal + 3.0, (peak, goal)                     # ไม่เด้งเลยเป้า
    assert m.shaped["yaw"] > yaw0 + 25.0, m.shaped["yaw"]       # หันตามคนได้ใน 2 วิ


def test_head_leads_body_when_turning_to_follow():
    """ผู้ใช้: ตอนตาม หัวนำก่อนแล้วตัวหมุนตาม -> คอเอียงไปทางเป้าก่อน ฐานตามทีหลัง แล้วคอกลับตรง"""
    from motion import MotionEngine, POSES
    from joints import NAMES
    P = dict(tempo=1.0, amp=0.0, lean=0.0, gaze_follow=1.0, brightness=0.8, warmth=1.0)
    m = MotionEngine({n: POSES["Curious"][n] for n in NAMES})
    for _ in range(90):
        m.step(1 / 30, "Curious", P, (0.0, 0.0))
    roll0 = m.shaped["head_roll"]
    t, peak, t_peak, t_yaw = 0.0, 0.0, None, None
    while t < 4.0:                                             # คนอยู่ทางซ้าย 35 องศา
        m.step(1 / 30, "Curious", P, (35.0, 0.0))
        t += 1 / 30
        r = m.shaped["head_roll"] - roll0
        if r < peak:
            peak, t_peak = r, t
        if t_yaw is None and m.shaped["yaw"] > 0.9 * 35.0:
            t_yaw = t
    assert peak < -8.0, peak                                   # หันซ้าย = เอียงคอซ้าย (roll ลบ) ชัดเจน
    assert t_peak < t_yaw, (t_peak, t_yaw)                     # คอนำก่อนฐานถึง
    assert abs(m.shaped["head_roll"] - roll0) < 2.0             # ฐานถึงแล้วคอกลับตรง


def test_ring_chases_while_tracking():
    """ผู้ใช้: ตอนมองตามอยู่ ไฟสีของอารมณ์นั้นวิ่งวน ; ไม่ได้ตาม = สีเต็มวง ; หมุนหันเร็ว = วิ่งเร็วขึ้น"""
    from led import Light
    class NP(list):
        writes = 0
        def write(self):
            NP.writes += 1
        def fill(self, c):
            for i in range(len(self)):
                self[i] = c
    def head(np):
        return max(range(len(np)), key=lambda i: sum(np[i]))
    np = NP([(0, 0, 0)] * 16)
    L = Light(neopixel=np, n=16, max_b=0.3)
    for i in range(40):
        L.update(1.0, 1.0, "Curious", i * 0.05, 0.05)
    assert len(set(np)) == 1                                   # ไม่ได้ตาม: ทุกเม็ดสีเดียวกัน
    L.update(1.0, 1.0, "Curious", 2.0, 0.05, track=0.05)
    assert len(set(np)) > 3                                    # ตาม: มีหัวสว่าง + หาง
    h0 = head(np)
    for i in range(10):
        L.update(1.0, 1.0, "Curious", 2.0 + i * 0.05, 0.05, track=0.05)
    slow = (head(np) - h0) % 16
    h1 = head(np)
    for i in range(10):
        L.update(1.0, 1.0, "Curious", 3.0 + i * 0.05, 0.05, track=1.0)
    fast = (head(np) - h1) % 16
    assert 0 < slow < fast, (slow, fast)                       # หมุนหันเร็ว ไฟวิ่งเร็วกว่า
    L.update(1.0, 1.0, "Curious", 4.0, 0.05)
    assert len(set(np)) == 1                                   # เลิกตาม กลับเป็นสีเต็มวง


def test_sickness_is_clearly_visible():
    """ผู้ใช้: ป่วยขอให้เห็นชัด -> หัวห้อย + หนาวสั่น + ไฟซีดและหายใจอ่อนแรง"""
    from motion import MotionEngine, POSES
    from joints import NAMES
    from led import Light, SICK_RGB
    def settle(warmth):
        P = dict(tempo=1.0, amp=0.0, lean=0.0, gaze_follow=0.0, brightness=0.8, warmth=warmth)
        m = MotionEngine({n: POSES["Idle"][n] for n in NAMES})
        rolls = []
        for i in range(240):
            m.step(1 / 30, "Idle", P, None)
            if i > 120:
                rolls.append(m.shaped["head_roll"])
        return m.shaped["head_pitch"], max(rolls) - min(rolls)
    pitch_ok, shake_ok = settle(1.0)
    pitch_sick, shake_sick = settle(0.0)
    assert pitch_sick < pitch_ok - 10.0, (pitch_ok, pitch_sick)          # หัวห้อยชัดเจน
    assert shake_sick > 2.0 and shake_ok < 0.5, (shake_ok, shake_sick)   # หนาวสั่น
    class NP(list):
        def write(self):
            pass
    np = NP([(0, 0, 0)] * 8)
    L = Light(neopixel=np, n=8, max_b=0.3)
    bs = []
    for i in range(120):
        rgb, b = L.update(0.8, 0.0, "Curious", i * 0.1, 0.1)
        if i > 60:
            bs.append(b)
    assert all(abs(a - s) <= 3 for a, s in zip(rgb, SICK_RGB)), rgb     # สีซีดเต็มที่
    assert max(bs) > 1.5 * min(bs), (min(bs), max(bs))                  # ไฟหายใจอ่อนแรง


def test_sick_mode_and_sleepy_sick_look():
    """ท่า Sick ใหม่ + ไฟซีด ; หลับตอนป่วยยังสั่น ("ง่วงแบบป่วยๆ")"""
    from motion import MotionEngine, POSES
    from joints import NAMES
    from led import EMOTION_RGB, SICK_RGB
    assert "Sick" in POSES and EMOTION_RGB["Sick"] == SICK_RGB
    P = dict(tempo=1.0, amp=0.0, lean=0.0, gaze_follow=0.0, brightness=0.5, warmth=0.1)
    m = MotionEngine({n: POSES["Sleep"][n] for n in NAMES})
    rolls = []
    for i in range(240):
        m.step(1 / 30, "Sleep", P, None)
        if i > 120:
            rolls.append(m.shaped["head_roll"])
    assert max(rolls) - min(rolls) > 2.0, max(rolls) - min(rolls)


def test_peek_face_is_straight():
    """ผู้ใช้: ตอนแอบดู หัวยังเอียงเหมือนท่าหลับ -> แอบดูหน้าตั้งตรง"""
    from motion import POSES
    assert abs(POSES["Peek"]["head_roll"]) <= 8 and POSES["Sleep"]["head_roll"] != 0   # ผู้ใช้จัดเอง: -6 = ตรงด้วยตา


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    fails = 0
    for n, f in tests:
        try:
            f()
            print("PASS  " + n)
        except Exception:
            fails += 1
            print("FAIL  " + n)
            traceback.print_exc()
    print("\n%d/%d passed" % (len(tests) - fails, len(tests)))
    sys.exit(1 if fails else 0)
