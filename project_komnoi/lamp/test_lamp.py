"""ชุดทดสอบตาม checklist หัวข้อ 14 ของ design notes (ข้อที่เกี่ยวกับโคม) : python test_lamp.py
ไม่ต้องใช้กล้อง/หน้าจอ ใช้นาฬิกาเสมือนจึงรันเร็ว"""
import math
import sys
import traceback

from ahm import Hormone, HormoneBank, ahm_health, decay_rate_for_half_life, alpha_for_equilibrium
from behavior import (LampBrain, BehaviorFSM, Arbiter, Event, Modulator, PARAM_SPECS)
from lamp import Lamp, ActuatorSafety, LIMITS, JOINTS
from perception import (Detection, FrameInfo, PerceptionEngine, Sample, validate)
from protocol import ControlPacket, SAFE_PARAMS
from vision import default_scenario

DT = 1 / 30


def drive(brain, scenario, t_end, t0=0.0, lamp=None, brightness=0.5, on_step=None):
    """รันสมอง (และโคม) ด้วยนาฬิกาเสมือน ; คืนรายการสถานะที่ผ่านมา"""
    t, nxt, pkt, states = t0, t0, None, []
    while t < t_end:
        brain.on_frame(FrameInfo(t=t, brightness=brightness, detections=scenario(t)), t)
        while t >= nxt:
            pkt = brain.tick(nxt)
            nxt += brain.cfg.slow_dt
            if not states or states[-1][1] != pkt.mode:
                states.append((round(t, 1), pkt.mode))
        if lamp is not None:
            lamp.step(DT, t, pkt)
        if on_step:
            on_step(t, pkt)
        t += DT
    return states


def quiet_brain(**kw):
    return LampBrain(alert=lambda m: None, **kw)


# ---------------------------------------------------------------- ฮอร์โมน
def test_half_life_and_equilibrium():
    k = decay_rate_for_half_life(2.0, 0.1)
    h = Hormone("x", alpha_for_equilibrium(0.7, 1.0, k), 0.7 * k, 0.3 * k)
    for i in range(2000):
        h.update(1.0, i * 0.1)
    assert abs(h.h - 0.7) < 0.01, h.h                      # H* ตามสูตร
    h.reset(0.8)
    for i in range(20):                                    # 2 วินาที = 1 ครึ่งชีวิต
        h.update(0.0, i * 0.1)
    assert abs(h.h - 0.4) < 0.02, h.h


def test_sustained_stimulus_never_hits_ceiling():
    b = HormoneBank()
    for i in range(3000):
        b.update({n: 1.0 for n in b.hormones}, i * 0.1)
    assert all(v < 0.95 for v in b.levels().values()), b.levels()   # เหลือที่ว่างแยกระดับได้


def test_short_pulses_dont_flip_behavior():
    br = quiet_brain()
    pulse = lambda t: [Detection(0.5, 0.5, 0.17, "face")] if (t % 1.0) < 0.2 else []
    states = drive(br, pulse, 30)
    assert len(states) <= 4, states                        # ไม่สลับรัวตามสิ่งเร้าสั้นๆ


def test_ahm_health_faults():
    h = Hormone("x", 0.05, 0.01, 0.01)
    h.update(0.0, 0.0)
    assert ahm_health(h, 0.1, 0, 0.5, 10) == "OK"
    assert ahm_health(h, 5.0, 0, 0.5, 10) == "FAULT_STALE"
    h.h = float("nan"); assert ahm_health(h, 0.1, 0, 0.5, 10) == "FAULT_VALUE"
    h.h = 0.99; h.last_update = 1.0; assert ahm_health(h, 1.1, 20, 0.5, 10) == "FAULT_STUCK"


def test_silent_ahm_triggers_alert_and_safe_default():
    alerts = []
    br = LampBrain(alert=alerts.append)
    drive(br, lambda t: [Detection(0.5, 0.5, 0.17, "face")], 12)
    br.bank.update = lambda stimuli, now: None             # โมดูลฮอร์โมนหยุดเงียบ
    drive(br, lambda t: [Detection(0.5, 0.5, 0.17, "face")], 14, t0=12)
    assert any("FAULT_STALE" in a for a in alerts), alerts
    assert br.bank.levels()["curiosity"] == 0.0            # ล้าง H
    p = br.last["params"]
    assert p["gaze_follow"] < 0.8                          # ไหลไปทาง safe default (ยังจำกัดอัตรา)


# ---------------------------------------------------------------- การรับรู้ / ข้อมูลเสีย
def test_validate_rejects_bad_data():
    now = 10.0
    for bad in (float("nan"), float("inf"), -1.0, 65535, 0, 99.0):
        assert validate(Sample(bad, now), now, 0.5, 5.0, 0.3, invalid_values=(0, 65535)) is None, bad
    assert validate(Sample(1.0, now - 1.0), now, 0.5, 5.0, 0.3) is None      # stale
    assert validate(None, now, 0, 1, 1) is None                              # timeout
    assert validate(Sample(1.0, now), now, 0.5, 5.0, 0.3) == 1.0


def test_nan_detection_ignored():
    e = PerceptionEngine()
    p = e.update(FrameInfo(t=0.1, detections=[Detection(float("nan"), 0.5, 0.2)]), 0.1)
    assert not p.present


def test_bad_frames_mean_unknown_not_normal():
    e = PerceptionEngine()
    for fi in (FrameInfo(t=1.0, ok=False), FrameInfo(t=float("nan")), FrameInfo(t=1.0, frozen=True),
               FrameInfo(t=0.0)):                                            # ตัวสุดท้าย = stale
        p = e.update(fi, 1.0)
        assert not p.valid and all(v is None for v in e.stimuli(p).values())


def test_camera_fault_then_recovery():
    br = quiet_brain()
    person = lambda t: [Detection(0.5, 0.5, 0.17, "face")]
    drive(br, person, 8)
    assert br.fsm.state in ("Curious", "Engage")
    cur_before = br.bank.levels()["curiosity"]
    t, nxt = 8.0, 8.0
    seen = []
    while t < 12.0:                                        # กล้องตาย 4 วินาที
        br.on_frame(FrameInfo(t=t, ok=False), t)
        while t >= nxt:
            br.tick(nxt); nxt += 0.1
        seen.append((round(t, 1), br.fsm.state))
        t += DT
    assert [s for tt, s in seen if tt < 9.8][-1] != "Blind"              # ยังไม่เกิน 2 วินาที: ยังไม่ตัดสิน
    assert br.fsm.state == "Blind"
    assert br.bank.levels()["curiosity"] <= cur_before + 1e-9            # ไม่เอาข้อมูลเสียไปสร้างฮอร์โมน
    assert any("Blind" in m for _, m in br.alerts), br.alerts          # แจ้งเตือน ไม่พังเงียบ
    drive(br, person, 14, t0=12.0)
    assert br.fsm.state != "Blind"


def test_dark_camera_makes_lamp_sleepy_stimulus():
    e = PerceptionEngine()
    for i in range(60):
        p = e.update(FrameInfo(t=i * DT, brightness=0.02, detections=[]), i * DT)
    assert e.stimuli(p)["sleepiness"] > 0.5


def test_zone_has_no_chatter_near_threshold():
    import random
    random.seed(3)
    e = PerceptionEngine()
    zs = []
    for i in range(400):
        h = 0.28 * 0.40 + random.uniform(-0.012, 0.012)
        zs.append(e.update(FrameInfo(t=i * DT, detections=[Detection(0.5, 0.5, h, "face")]), i * DT).zone)
    assert sum(1 for a, b in zip(zs[10:], zs[11:]) if a != b) <= 2


def test_habituation_second_visit_less_novel():
    e = PerceptionEngine()
    nov = []
    t = 0.0
    for visit in range(3):
        for i in range(60):
            e.update(FrameInfo(t=t, detections=[Detection(0.5, 0.5, 0.15, "face")]), t); t += DT
        nov.append(e.percept.novelty)
        for i in range(90):
            e.update(FrameInfo(t=t, detections=[]), t); t += DT
    assert nov[0] > nov[1] > nov[2], nov


# ---------------------------------------------------------------- ปฏิกิริยา
def test_popin_close_triggers_startle_fast_but_slow_approach_does_not():
    br = quiet_brain()
    st = drive(br, lambda t: [] if t < 2 else [Detection(0.5, 0.5, 0.36, "face")], 4)
    shy_t = [t for t, s in st if s == "Fear"]
    assert shy_t and shy_t[0] - 2.0 < 0.6, st                           # สะดุ้งใน ~0.5 วินาที (เร็วกว่าฮอร์โมน)
    br = quiet_brain()
    slow = lambda t: [Detection(0.5, 0.5, 0.06 + 0.012 * t, "face")]    # ค่อยๆ เข้ามา
    st = drive(br, slow, 12)
    assert "Fear" not in [s for _, s in st], st


def test_scripted_story_order():
    br = quiet_brain()
    seq = [s for _, s in drive(br, default_scenario, 105)]
    want = ["Curious", "Engage", "Fear", "Sleep"]
    it = iter(seq)
    assert all(any(w == s for s in it) for w in want), seq               # ต้องเกิดตามลำดับนี้ (subsequence)


def test_wake_from_sleep_reduces_sleepiness():
    br = quiet_brain()
    drive(br, lambda t: [], 90)
    assert br.fsm.state == "Sleep"
    before = br.bank.levels()["sleepiness"]
    drive(br, lambda t: [Detection(0.5, 0.5, 0.15, "face")], 94, t0=90)
    assert br.fsm.state != "Sleep" and br.bank.levels()["sleepiness"] < before * 0.6


# ---------------------------------------------------------------- arbiter / guard / dwell
def fsm_at(state, since=0.0):
    f = BehaviorFSM(Arbiter(0.5), 1.2, start=state, now=since)
    return f


def test_state_guard_shy_ignores_lower_priority():
    f = fsm_at("Fear")
    f.arbiter.last_state_change = 0.0
    for kind in ("target_seen", "target_engaged", "sleepy", "wake", "target_lost"):
        assert f.step([Event(kind, 5.0)], 5.0) == "Fear", kind
    assert f.step([Event("startle_clear", 5.0)], 5.0) == "Idle"


def test_state_guard_engage_not_interrupted_by_sleepy_and_blind_only_by_sensor_ok():
    f = fsm_at("Engage"); f.arbiter.last_state_change = 0.0
    assert f.step([Event("sleepy", 5.0)], 5.0) == "Engage"
    f = fsm_at("Blind"); f.arbiter.last_state_change = 0.0
    for kind in ("startle", "target_seen", "sleepy", "target_lost"):
        assert f.step([Event(kind, 5.0)], 5.0) == "Blind", kind
    assert f.step([Event("sensor_ok", 5.0)], 5.0) == "Idle"


def test_stale_events_dropped_but_safety_passes():
    f = fsm_at("Idle"); f.arbiter.last_state_change = 0.0
    assert f.step([Event("target_seen", 1.0)], 5.0) == "Idle"            # ข้อมูลเก่า 4 วินาที -> ทิ้ง
    assert f.step([Event("sensor_lost", 1.0)], 5.0) == "Blind"           # ระดับความปลอดภัยผ่านเสมอ


def test_min_dwell_prevents_flicker():
    f = fsm_at("Idle", since=-5.0); f.arbiter.last_state_change = -5.0
    assert f.step([Event("target_seen", 1.0)], 1.0) == "Curious"
    assert f.step([Event("target_lost", 1.5)], 1.5) == "Curious"         # อยู่ไม่ถึง 1.2 วินาที
    assert f.step([Event("target_lost", 2.6)], 2.6) == "Idle"


def test_modulator_bounds_and_slew_and_inhibition():
    m = Modulator()
    e = {"caution": 1.0, "curiosity": 1.0, "affinity": 1.0, "sleepiness": 1.0}
    prev = m.values()
    for _ in range(100):
        cur = m.update(e)
        for k, sp in PARAM_SPECS.items():
            assert sp.lo - 1e-9 <= cur[k] <= sp.hi + 1e-9
            assert abs(cur[k] - prev[k]) <= sp.max_step + 1e-9
        prev = cur
    assert Modulator.resolve({"caution": 1.0, "curiosity": 1.0, "affinity": 1.0})["curiosity"] == 0.0


# ---------------------------------------------------------------- ฝั่งโคม (fast loop)
def test_actuator_safety_clamp_slew_nan_resync():
    s = ActuatorSafety(LIMITS, cmd_timeout=0.3)
    lim = LIMITS["shoulder"]
    out = s.filter("shoulder", 500.0, 0.0, 0.0, 0.0, 0.01)
    assert out <= lim.max_rate * 0.01 + 1e-9                             # slew
    x = 0.0
    for i in range(400):
        x = s.filter("shoulder", 500.0, i * 0.01, x, i * 0.01, 0.01)
    assert x <= lim.soft_max + 1e-9                                      # clamp
    assert s.filter("shoulder", float("nan"), 5.0, x, 5.0, 0.01) == x    # NaN -> ค้างท่า
    assert s.filter("shoulder", 10.0, 3.0, x, 5.1, 0.01) == x            # คำสั่งเก่า -> ค้างท่า
    s.prev["shoulder"] = -50.0                                           # คำสั่งเก่าที่ค้างอยู่ห่างจากมุมจริง
    out = s.filter("shoulder", 20.0, 6.0, 30.0, 6.0, 0.01)               # กลับมา: ไล่จากมุมจริง (30) ไม่ใช่ -50
    assert abs(out - 30.0) <= lim.max_rate * 0.01 + 1e-9


def test_lamp_never_exceeds_slew_or_limits_through_full_story():
    br, lamp = quiet_brain(), Lamp()
    prev = dict(lamp.angles)
    worst = {j: 0.0 for j in JOINTS}

    def check(t, pkt):
        for j in JOINTS:
            d = abs(lamp.angles[j] - prev[j]); worst[j] = max(worst[j], d)
            assert d <= LIMITS[j].max_rate * DT * 1.001 + 1e-9, (j, d, t)
            assert LIMITS[j].soft_min - 1e-9 <= lamp.angles[j] <= LIMITS[j].soft_max + 1e-9
            prev[j] = lamp.angles[j]
    drive(br, default_scenario, 105, lamp=lamp, on_step=check)


def test_lamp_stale_or_nan_packet_goes_safe():
    lamp = Lamp()
    good = ControlPacket(t=1.0, mode="Engage", params=dict(SAFE_PARAMS), gaze=(10.0, 0.0))
    lamp.step(DT, 1.0, good); assert not lamp.stale and lamp.mode == "Engage"
    lamp.step(DT, 3.0, good); assert lamp.stale and lamp.mode == "Blind"     # สมองเงียบ
    bad = ControlPacket(t=3.0, mode="Engage", params=dict(SAFE_PARAMS, amp=float("nan")))
    lamp.step(DT, 3.0, bad); assert lamp.stale                               # พารามิเตอร์เสีย
    assert all(math.isfinite(v) for v in lamp.angles.values())
    lamp.step(DT, 3.1, None); assert lamp.stale                              # ไม่มีแพ็กเก็ตเลย


def test_gaze_follows_person_direction():
    lamp = Lamp()
    P = dict(tempo=1.0, amp=1.0, lean=0.0, gaze_follow=1.0, brightness=0.8, warmth=0.5)
    t = 0.0
    for i in range(240):
        t += DT
        lamp.step(DT, t, ControlPacket(t=t, mode="Engage", params=P, gaze=(25.0, 0.0)))
    assert 15 < lamp.angles["yaw"] < 32, lamp.angles["yaw"]                  # หันตามไปทางซ้าย (+)


def test_sim_matches_firmware_poses_and_limits():
    """กฎข้อ 8: POSES/LIMITS ฝั่งโน้ตบุ๊กต้องตรงกับฝั่งบอร์ด และทุกท่าต้องอยู่ในช่วง"""
    import os
    from lamp import POSES as SIM_POSES
    fw = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lamp_firmware")
    sys.path.append(fw)
    try:
        import config as fw_cfg
        from motion import POSES as FW_POSES
    finally:
        sys.path.remove(fw)
    fw_lim = {r[0]: (r[4], r[5], r[6]) for r in fw_cfg.JOINTS}
    for j in fw_lim:                 # ซิมมีข้อต่อครบ 5 ตัว บอร์ดใช้เท่าที่ใช้งานได้
        sim = (LIMITS[j].soft_min, LIMITS[j].soft_max, LIMITS[j].max_rate)
        assert sim == fw_lim[j], (j, sim, fw_lim[j])
    for mode, row in SIM_POSES.items():
        fw_pose = FW_POSES[mode]
        for j, v in zip(JOINTS, row):
            assert v == fw_pose[j], (mode, j, v, fw_pose[j])
            assert LIMITS[j].soft_min <= v <= LIMITS[j].soft_max, (mode, j, v)


def test_sickness_fast_onset_slow_recovery():
    """จุ่มน้ำ 10 วิ -> ป่วยชัด ; ยกออก -> หายช้า (ครึ่งชีวิต ~90 วิ)"""
    from ahm import HormoneBank
    b = HormoneBank(slow_dt=0.1)
    t = 0.0
    for _ in range(100):                                   # จุ่ม 10 วิ
        t += 0.1
        b.update({"sickness": 1.0}, t)
    peak = b.levels()["sickness"]
    assert peak > 0.4, peak
    for _ in range(300):                                   # ยกออก 30 วิ ยังป่วยอยู่มาก
        t += 0.1
        b.update({"sickness": 0.0}, t)
    assert b.levels()["sickness"] > 0.7 * peak, (peak, b.levels()["sickness"])
    for _ in range(600):                                   # อีก 60 วิ (รวม 90) เหลือราวครึ่ง
        t += 0.1
        b.update({"sickness": 0.0}, t)
    assert 0.4 * peak < b.levels()["sickness"] < 0.6 * peak


def test_care_speeds_recovery_only_for_sickness():
    from ahm import HormoneBank
    def run(care):
        b = HormoneBank(slow_dt=0.1)
        t = 0.0
        for _ in range(100):
            t += 0.1
            b.update({"sickness": 1.0, "affinity": 1.0}, t)
        for _ in range(150):                               # 15 วิหลังยกออก
            t += 0.1
            b.update({"sickness": 0.0, "care": care}, t)
        return b.levels()
    plain, cared = run(0.0), run(1.0)
    assert cared["sickness"] < 0.6 * plain["sickness"], (plain, cared)   # ลูบหัว 15 วิ ~ลดอีกครึ่ง
    assert abs(cared["affinity"] - plain["affinity"]) < 1e-9             # care ไม่ไปลดฮอร์โมนอื่น
    b = HormoneBank(slow_dt=0.1)
    b.update({"sickness": 1.0, "care": float("nan")}, 0.1)               # ค่าเสียต้องไม่พัง
    assert 0.0 <= b.levels()["sickness"] <= 1.0


def test_sickness_dampens_curiosity_and_amplifies_startle():
    from behavior import Modulator
    well = Modulator.resolve({"curiosity": 0.8, "sleepiness": 0.1, "caution": 0.2})
    sick = Modulator.resolve({"curiosity": 0.8, "sleepiness": 0.1, "caution": 0.2, "sickness": 1.0})
    assert sick["curiosity"] < 0.4 * well["curiosity"]
    assert sick["sleepiness"] >= well["sleepiness"] + 0.49
    assert sick["caution"] > well["caution"]
    assert all(0.0 <= v <= 1.0 for v in sick.values())
    m = Modulator()
    for _ in range(200):
        p = m.update({"sickness": 1.0, "sleepiness": 1.0, "caution": 1.0})
    from behavior import PARAM_SPECS
    for n, v in p.items():                                 # ป่วยหนักแค่ไหน ก็ยังอยู่ในขอบ
        assert PARAM_SPECS[n].lo <= v <= PARAM_SPECS[n].hi, (n, v)


# ---------------------------------------------------------------- เซนเซอร์แทนกล้อง
def _sensor_run(T, feed=None, keys_at=()):
    """รันสมองด้วย SensorPerception ; feed(t) -> tlm dict หรือ None (ไม่มีข้อมูล)"""
    from sensor_perception import SensorPerception
    from sensor_sim import ScriptedSensors
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    src = ScriptedSensors(0.0)
    feed = feed or src.read
    log, t, nxt = [], 0.0, 0.0
    while t < T:
        brain.on_frame(feed(t), t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            L = brain.last
            log.append((t, L["state"], dict(L["H"]), dict(L["params"]), dict(L["S"])))
        t = round(t + 0.02, 4)
    return log, sp


def _state_at(log, t):
    return min(log, key=lambda r: abs(r[0] - t))


def test_sensor_story_matches_expected_emotions():
    log, _ = _sensor_run(110.0)
    states = [r[1] for r in log]
    seq = [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]
    assert seq[:4] == ["Idle", "Curious", "Engage", "Fear"], seq          # เข้ามา -> สนใจ -> ผูกพัน -> ตบ
    assert all(_state_at(log, t)[1] == "Idle" for t in (2, 5, 9, 10)), "คนโผล่ไกลๆ ต้องไม่ตกใจ"
    assert _state_at(log, 33)[1] == "Fear"                                 # ตบหัวที่ 32
    assert any(r[1] == "Fear" for r in log if 62.0 < r[0] < 64.0)          # พุ่งเข้าหาที่ 62
    assert _state_at(log, 100.5)[1] == "Sleep"                            # ไม่มีใครนาน
    assert _state_at(log, 102.5)[1] != "Sleep"                            # กดปลุกที่ 101
    t_cur = next(r[0] for r in log if r[1] == "Curious")
    t_eng = next(r[0] for r in log if r[1] == "Engage")
    assert t_cur >= 12.0 + 2.0 and t_eng - t_cur >= 4.0, (t_cur, t_eng)   # เข้าระยะ 70 ซม. ที่ 12 วิ: สนใจหลัง 2 วิ


def test_sickness_from_water_changes_expression_not_safety():
    log, _ = _sensor_run(70.0)
    before, sick = _state_at(log, 40.5), _state_at(log, 52.5)
    assert sick[2]["sickness"] > 0.4 and before[2]["sickness"] < 0.02
    assert sick[3]["lean"] < before[3]["lean"] - 0.1                      # ป่วยแล้วโน้มเข้าหาน้อยลง
    assert sick[3]["tempo"] < before[3]["tempo"] - 0.15                   # ขยับช้าลง
    cared = _state_at(log, 59.5)[2]["sickness"]
    assert cared < sick[2]["sickness"] - 0.05                             # ลูบหัวช่วยให้หาย


def test_target_jump_is_not_rush():
    """ผนัง 2.6 m -> คนเดินตัดหน้าที่ 0.9 m ทันที : ไม่ใช่ \"พุ่งเข้าหา\" ไม่ต้องสะดุ้ง"""
    def feed(t):
        return {"dist_m": 2.6 if t < 3 else 0.9, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t}
    log, sp = _sensor_run(6.0, feed)
    assert all(r[1] != "Fear" for r in log), [r[1] for r in log if r[1] == "Fear"][:3]
    assert all((r[4]["caution"] or 0.0) < 0.5 for r in log)


def test_stale_or_missing_sensor_goes_blind_with_safe_params():
    def feed(t):
        if t < 3:
            return {"dist_m": 0.7, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t}
        return None                                                       # ลิงก์หลุด
    log, _ = _sensor_run(7.0, feed)
    assert _state_at(log, 6.5)[1] == "Blind"
    last = log[-1]
    assert last[4]["sickness"] is None and last[4]["curiosity"] is None   # ไม่รู้ = None ไม่ใช่ 0


def test_key_seq_counts_new_presses_only():
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    base = {"dist_m": 0.7, "wet": 0.0}
    sp.update(dict(base, key="7", key_seq=5, t_rx=0.0), 0.0)             # ปุ่มเก่าก่อนเชื่อมต่อ: ไม่นับ
    assert sp.presses == []
    sp.update(dict(base, key="1", key_seq=6, t_rx=0.1), 0.1)
    sp.update(dict(base, key="1", key_seq=6, t_rx=0.2), 0.2)             # เฟรมซ้ำ ไม่นับซ้ำ
    sp.update(dict(base, key="1", key_seq=7, t_rx=0.3), 0.3)             # กดปุ่มเดิมอีกครั้ง นับ
    assert [k for _, k in sp.presses] == ["1", "1"]
    S = sp.stimuli(sp.percept)
    assert S["affinity"] == 1.0 and S["care"] == 1.0


def test_link_py_identical_on_both_sides():
    """กฎข้อ 8: link.py ฝั่งโน้ตบุ๊กกับฝั่งบอร์ดต้องเป็นไฟล์เดียวกัน (ไม่งั้นถอด telemetry เพี้ยน)"""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    a = open(os.path.join(here, "link.py"), "rb").read()
    b = open(os.path.join(here, "..", "lamp_firmware", "link.py"), "rb").read()
    assert a == b, "link.py สองฝั่งไม่ตรงกัน -- ก็อปจาก lamp_firmware/link.py มาทับ"


# ---------------------------------------------------------------- เซนเซอร์บนหัว: ไม่กลัวตัวเอง
def _tl(t, d, joints=None):
    return {"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
            "joints": joints or [(0.0, 0, 20)] * 5}


def test_static_self_occlusion_does_not_trap_in_shy():
    """บั๊กจริงบนหุ่น: หัวเห็นตัวเองที่ 4-8 ซม. นิ่งๆ -> caution ค้าง 0.8 -> Fear ไม่ออก"""
    import math
    def feed(t):
        return _tl(t, 0.05 + 0.005 * math.sin(7 * t))       # สั่นแค่ +-5 มม. (สัญญาณรบกวน)
    log, sp = _sensor_run(20.0, feed)
    late = [r for r in log if r[0] > 12.0]
    assert all((r[4]["caution"] or 0.0) == 0.0 for r in late), "ใกล้แต่นิ่งนาน ต้องชินแล้ว"
    assert log[-1][1] != "Fear", [r[1] for r in log[-20:]]


def test_real_approach_to_too_close_still_startles():
    """คนยืนอยู่แล้ว (โคมสนใจและนิ่งแล้ว) แล้วยื่นมือพุ่งเข้ามา -> ต้องยังกลัว"""
    import math
    def feed(t):
        if t < 8.0:
            d = 0.45 + 0.04 * math.sin(2 * math.pi * 0.35 * t)
        else:
            d = max(0.08, 0.45 - (t - 8.0) * 0.6)                  # มือพุ่งเข้ามา 0.6 ม./วิ
        return _tl(t, d)
    log, _ = _sensor_run(10.5, feed)
    assert any(r[1] == "Curious" for r in log if r[0] < 8.0)
    assert any(r[1] == "Fear" for r in log if 8.5 < r[0] < 10.5), [r[1] for r in log if r[0] > 8][:30]


def test_leaning_in_toward_a_still_hand_is_not_scary():
    """บั๊กจริงบนหุ่น: มือยื่นค้างไว้ โคมเข้า Curious แล้วโน้มเข้าหามือเอง ระยะ 0.30 -> 0.12 -> นึกว่ามือพุ่งมา -> กลัว"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, t_cur, states = 0.0, 0.0, None, []
    while t < 15.0:
        st = brain.last.get("state") if brain.last else "Idle"
        if st == "Curious" and t_cur is None:
            t_cur = t
        if t < 2.0:
            d = 2.4
        elif t_cur is None:
            d = 0.30 + 0.01 * math.sin(5 * t)                      # มือค้างอยู่ตรงหน้า
        else:
            d = max(0.12, 0.30 - (t - t_cur) * 0.09)               # โคมโน้มเข้าหาเอง 2 วิ
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                        "joints": [(0, 0, 20)] * 5}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            states.append(brain.last["state"])
        t = round(t + 0.05, 4)
    assert t_cur is not None, "ต้องสนใจก่อน"
    assert "Fear" not in states, states


def test_self_motion_reveals_table_is_background():
    """corollary discharge: โคมก้มหัวเอง แล้วเซนเซอร์เห็นโต๊ะที่ 0.12 m -> ไม่ใช่สิ่งที่พุ่งเข้าหา ไม่ตกใจ"""
    def feed(t):
        if t < 2:
            return _tl(t, 1.5)
        if t < 3:                                             # หัวกำลังก้ม (head_pitch ขยับ 60 องศา/วิ)
            a = (t - 2) * 60.0
            return _tl(t, 1.5 - (t - 2) * 1.38, [(0, 0, 20), (0, 0, 20), (0, 0, 20), (a, 0, 20), (0, 0, 20)])
        return _tl(t, 0.12, [(0, 0, 20), (0, 0, 20), (0, 0, 20), (60.0, 0, 20), (0, 0, 20)])
    log, sp = _sensor_run(8.0, feed)
    assert all(r[1] != "Fear" for r in log), [r[1] for r in log if r[1] == "Fear"][:3]
    assert all((r[4]["caution"] or 0.0) < 0.5 for r in log)


def test_still_object_becomes_background_not_a_person():
    """วัตถุนิ่งในระยะสนใจ (กล่องบนโต๊ะ) -> สนใจแค่พักเดียว แล้วไม่นับว่ามีคน (ไม่ค้าง Curious/Engage)"""
    log, sp = _sensor_run(30.0, lambda t: _tl(t, 0.7))
    assert sp.percept.present is False
    assert (log[-1][4]["curiosity"] or 0.0) == 0.0


def test_person_stays_a_person_across_own_pose_change():
    """บั๊กจริงบนหุ่น: เปลี่ยนท่าแล้วคนที่ยืนนิ่งกลายเป็นฉากหลัง -> กลับ Idle ทันที"""
    import math
    def feed(t):
        d = 0.45 + 0.005 * math.sin(3 * t)                       # คนยืนนิ่งมาก
        j = [(0, 0, 20)] * 5
        if 3.0 <= t < 3.6:                                        # โคมเปลี่ยนท่าเอง หัวกวาด ระยะเพี้ยนชั่วคราว
            a = (t - 3.0) * 100.0
            j = [(0, 0, 20), (a, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]
            d = 1.4
        elif t >= 3.6:
            j = [(0, 0, 20), (60.0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]
        return _tl(t, d, j)
    log, sp = _sensor_run(8.0, feed)
    assert sp.percept.present, "คนเดิมหลังโคมขยับต้องยังนับว่ามีคน"
    assert (log[-1][4]["curiosity"] or 0.0) > 0.3


def test_own_motion_sweep_does_not_wake_from_sleep():
    """บั๊กจริงบนหุ่น: เข้าท่า Sleep หัวกวาด เห็นของที่ 0.83 m ชั่วขณะ -> นึกว่ามีคน -> ตื่นทันที"""
    def feed(t):
        j = [(0, 0, 20)] * 5
        d = 2.4
        if 60.0 <= t < 61.0:                                     # เปลี่ยนท่า: หัวกวาด เห็นของใกล้ชั่วขณะ
            a = (t - 60.0) * 80.0
            j = [(0, 0, 20), (a, 0, 20), (0, 0, 20), (a, 0, 20), (0, 0, 20)]
            d = 0.83
        elif t >= 61.0:
            j = [(0, 0, 20), (80.0, 0, 20), (0, 0, 20), (80.0, 0, 20), (0, 0, 20)]
        return _tl(t, d, j)
    log, sp = _sensor_run(66.0, feed)
    assert all(not r[4] is None for r in log)
    present_during = [r for r in log if 60.0 <= r[0] < 62.0]
    assert sp.percept.present is False
    assert all(r[2]["sleepiness"] > 0.3 for r in present_during), "หัวกวาดเองต้องไม่ทำให้หายง่วง"


def _sleep_world(T, scene, keys=()):
    """รันสมองโดยให้ "ฉาก" ขึ้นกับท่าที่ส่งไปจริง: scene(t, out_mode, since_mode) -> ระยะ
    keys = [(เวลา, ปุ่ม)] ; คืน [(เวลา, state, out_mode)]"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, log = 0.0, 0.0, []
    mode, mode_since, kseq, pend = "Idle", 0.0, 0, list(keys)
    while t < T:
        if brain.last:
            m = brain.last["packet"].mode
            if m != mode:
                mode, mode_since = m, t
        key = None
        if pend and t >= pend[0][0]:
            key, kseq = pend.pop(0)[1], kseq + 1
        d = scene(t, mode, t - mode_since)
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": key, "key_seq": kseq, "t_rx": t,
                        "joints": [(0, 0, 20)] * 5}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], brain.last["packet"].mode))
        t = round(t + 0.05, 4)
    return log, sp


NOISY = [0.15, 0.11, 0.12, 0.18, 0.04, 0.12, 0.13, 0.11, 0.16, 0.12, 0.05, 0.12, 0.14, 0.11, 0.12, 0.17, 0.06]


def _table(t, since):
    """ท่า Sleep: หัวทรุดลงเห็นโต๊ะ (ค่อยๆ ลดใน 2.5 วิ แล้วแกว่งแรงแบบที่เห็นบนหุ่นจริง)"""
    if since < 2.5:
        return max(0.12, 2.4 - since * 0.95)
    return NOISY[int(t * 20) % len(NOISY)]


def test_sleep_ignores_noisy_table_and_peeks_without_waking():
    """หุ่นจริง: หลับแล้วหัวเห็นโต๊ะ ค่าแกว่ง 0.04-0.18 -> ต้องไม่ตกใจ ไม่ตื่น ; แอบดูเป็นระยะแล้วหลับต่อ"""
    log, _ = _sleep_world(170.0, lambda t, m, s: _table(t, s) if m == "Sleep" else 2.4)
    slept = [i for i, r in enumerate(log) if r[1] == "Sleep"]
    assert slept, "ต้องหลับก่อน"
    after = log[slept[0]:]
    assert all(r[1] == "Sleep" for r in after), sorted(set(r[1] for r in after))   # ไม่ตื่น ไม่ Fear
    assert any(r[2] == "Peek" for r in after), "ต้องมีการแอบดู (ส่งท่า Peek ชั่วคราว)"
    assert after[-1][2] in ("Sleep", "Peek")


def test_person_arriving_while_asleep_is_seen_only_at_next_peek():
    """หลับตาอยู่ไม่รู้ว่ามีคนมา ; ตอนแอบดูเห็นคน -> ตื่นจริง แล้วสนใจ"""
    arrive = [None]
    def scene(t, m, s):
        if m == "Sleep":
            return _table(t, s)
        if arrive[0] is not None and t >= arrive[0]:
            return 0.45 + 0.04 * math.sin(2 * math.pi * 0.35 * t)  # คนยืนโยกตัวตรงหน้า
        return 2.4
    import math
    # หาเวลาเริ่มหลับก่อน แล้วให้คนมาหลังหลับ 5 วิ
    log0, _ = _sleep_world(120.0, lambda t, m, s: _table(t, s) if m == "Sleep" else 2.4)
    t_sleep = next(r[0] for r in log0 if r[1] == "Sleep")
    arrive[0] = t_sleep + 5.0
    log, _ = _sleep_world(t_sleep + 45.0, scene)
    before_peek = [r for r in log if arrive[0] <= r[0] < arrive[0] + 10.0]
    assert all(r[1] == "Sleep" for r in before_peek), "หลับตาอยู่ ต้องยังไม่รู้ว่ามีคน"
    woke = [r for r in log if r[0] > arrive[0] and r[1] != "Sleep"]
    assert woke, "แอบดูแล้วเห็นคน ต้องตื่น"
    assert any(r[1] == "Curious" for r in log if r[0] > woke[0][0]), "ตื่นแล้วต้องสนใจคน"


def test_only_key5_works_while_asleep():
    log0, _ = _sleep_world(120.0, lambda t, m, s: _table(t, s) if m == "Sleep" else 2.4)
    t_sleep = next(r[0] for r in log0 if r[1] == "Sleep")
    keys = [(t_sleep + 4.0, "7"), (t_sleep + 5.0, "1"), (t_sleep + 8.0, "5")]
    log, sp = _sleep_world(t_sleep + 12.0, lambda t, m, s: _table(t, s) if m == "Sleep" else 2.4, keys)
    mid = [r for r in log if t_sleep + 4.0 <= r[0] < t_sleep + 7.9]
    assert all(r[1] == "Sleep" for r in mid), "ตบ/ลูบตอนหลับ ต้องไม่สนใจ"
    assert [k for _, k in sp.ignored_presses] == ["7", "1"]
    assert log[-1][1] != "Sleep", "ปุ่ม 5 ต้องปลุกได้"


def _angle_world(T, person_at, w=0.9):
    """โลกจำลองมีทิศ: ฐานหมุนตาม gaze ของสมอง (x w) ; ลำแสงกว้าง +-10 องศา
    person_at(t) -> มุมของคน (None = ไม่มีคน)"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, yaw, log = 0.0, 0.0, 0.0, []
    while t < T:
        L = brain.last
        g = L["packet"].gaze if L else None
        target = (g[0] * w) if g else 0.0
        yaw += max(-1.5, min(1.5, target - yaw))                 # ฐานหมุนได้ ~30 องศา/วิ
        a = person_at(t)
        d = 0.45 + 0.03 * math.sin(2.2 * t) if (a is not None and abs(yaw - a) < 10.0) else 2.4
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                        "joints": [(yaw, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], yaw, brain.last["searching"]))
        t = round(t + 0.05, 4)
    return log


def test_curious_follows_person_who_steps_aside():
    """สนใจแล้วคนเดินไปด้านข้าง 40 องศา -> กวาดหาจนเจอ แล้วค้างมองตรงนั้น ไม่กลับ Idle"""
    log = _angle_world(25.0, lambda t: 0.0 if t < 8.0 else 40.0)
    assert any(r[1] == "Curious" for r in log if r[0] < 8.0)
    after = [r for r in log if r[0] >= 8.0]
    assert all(r[1] in ("Curious", "Engage") for r in after), sorted(set(r[1] for r in after))
    assert any(r[3] for r in after), "ต้องมีการกวาดหา"
    assert abs(log[-1][2] - 40.0) < 12.0 and not log[-1][3], (log[-1][2], log[-1][3])


def test_scan_gives_up_when_person_really_left():
    """คนเดินออกไปจริง -> กวาดครบสองฝั่ง แล้วกลับ Idle หันกลับมาตรง"""
    log = _angle_world(38.0, lambda t: 0.0 if t < 8.0 else None)
    assert any(r[3] for r in log if r[0] >= 8.0)
    assert log[-1][1] == "Idle" and abs(log[-1][2]) < 5.0, log[-1]


def test_sleep_lasts_8_minutes_then_wakes_rested():
    """หลับแล้วความง่วงค้าง 8 นาที แล้วค่อยๆ ลดจนตื่นเอง ; ตื่นแล้วไม่ง่วงซ้ำทันที"""
    log, _ = _sleep_world(720.0, lambda t, m, s: _table(t, s) if m == "Sleep" else 2.4)
    t_sleep = next(r[0] for r in log if r[1] == "Sleep")
    t_wake = next(r[0] for r in log if r[0] > t_sleep and r[1] != "Sleep")
    assert 480.0 <= t_wake - t_sleep <= 600.0, (t_sleep, t_wake)
    after = [r for r in log if t_wake <= r[0] < t_wake + 110.0]
    assert all(r[1] != "Sleep" for r in after), "ตื่นแล้วต้องสดชื่น ไม่หลับซ้ำทันที"


def test_engage_fades_back_to_curious_when_nothing_new_happens():
    """ผูกพันแล้วอยู่เฉยๆ นาน (ไม่ลูบหัวต่อ) -> ความผูกพันค่อยๆ ลด -> กลับไปสนใจ"""
    import math
    keys = [(t, "1") for t in range(6, 30, 2)]
    def feed(t):
        kseq = sum(1 for kt, _ in keys if t >= kt)
        last = keys[kseq - 1][1] if kseq else None
        d = 0.6 + 0.04 * math.sin(2 * math.pi * 0.35 * t)
        return {"dist_m": d, "wet": 0.0, "key": last, "key_seq": kseq, "t_rx": t, "joints": [(0, 0, 20)] * 5}
    log, _ = _sensor_run(160.0, feed)
    t_eng = next(r[0] for r in log if r[1] == "Engage")
    assert any(r[1] == "Curious" for r in log if r[0] > t_eng + 10.0), "ผูกพันต้องจางลงได้"


def test_web_ui_history_and_command_queue():
    """เว็บแดชบอร์ด: เก็บประวัติแค่ 2 นาที ; คำสั่งจากเว็บเข้าคิวให้ลูปหลักดึงไปทำ"""
    import web_ui
    ui = web_ui.WebUI(port=0)
    for i in range(400):                                   # 200 วินาที ทุก 0.5 วิ
        t = i * 0.5
        ui.push(t, {"t": t, "state": "Idle", "H": {"caution": 0.1, "curiosity": 0.2, "affinity": 0.3,
                                                   "sleepiness": 0.4, "sickness": 0.5}})
    assert ui.history[0][0] >= 199.5 - web_ui.HISTORY_S - 1e-6
    assert len(ui.history) <= int(web_ui.HISTORY_S / web_ui.SAMPLE_S) + 2
    ui.cmds.put(("key", "1"))
    ui.cmds.put(("dip", None))
    assert ui.commands() == [("key", "1"), ("dip", None)] and ui.commands() == []


def test_key4_treatment_speeds_up_recovery():
    """ผู้ใช้: ป่วยแล้วเอาปุ่ม 4 (เดิมสะกิด) เป็น "รักษา" ให้หายเร็วขึ้น"""
    def run(keys):
        def feed(t):
            kseq = sum(1 for kt in keys if t >= kt)
            return {"dist_m": 2.4, "wet": 1.0 if t < 12.0 else 0.0, "key": "4" if kseq else None,
                    "key_seq": kseq, "t_rx": t, "joints": [(0, 0, 20)] * 5}
        log, sp = _sensor_run(30.0, feed)
        return _state_at(log, 29.5)[2]["sickness"], sp
    plain, _ = run(())
    treated, sp = run((14.0, 16.0, 18.0))
    assert treated < plain * 0.5, (treated, plain)
    assert [k for _, k in sp.presses] == ["4", "4", "4"]


def test_fear_grows_with_approach_speed():
    """ผู้ใช้: เข้ามาเร็วๆ แล้วไม่ค่อยกลัว -> ยิ่งเร็วยิ่งกลัว ; ค่อยๆ โน้มเข้ามาช้าๆ ไม่กลัว"""
    import math
    def approach(speed):
        def feed(t):                                           # ยืนในระยะจนโคมสนใจและนิ่งแล้ว จึงเข้ามา
            d = 0.65 if t < 10.0 else max(0.25, 0.65 - (t - 10.0) * speed)
            return _tl(t, d + 0.01 * math.sin(3.0 * t))
        log, _ = _sensor_run(13.0, feed)
        return max(r[2]["caution"] for r in log if r[0] > 10.0), [r[1] for r in log if r[0] > 10.0]
    slow_h, slow_s = approach(0.3)
    mid_h, _ = approach(0.9)
    fast_h, fast_s = approach(1.5)
    assert slow_h < 0.05 and "Fear" not in slow_s, slow_h          # โน้มเข้ามาช้าๆ ไม่กลัว
    assert mid_h > slow_h + 0.05, (slow_h, mid_h)                  # เร็วปานกลาง อะดรีนาลีนขึ้น
    assert "Fear" in fast_s, fast_h                                # เร็วมาก สะดุ้งกลัว

def test_detection_range_is_70cm():
    """ผู้ใช้: 2 ม. เยอะไป ขอ 70 ซม."""
    import math
    log, sp = _sensor_run(10.0, lambda t: _tl(t, 0.62 + 0.04 * math.sin(2 * math.pi * 0.35 * t)))
    assert sp.percept.present
    log, sp = _sensor_run(10.0, lambda t: _tl(t, 1.0 + 0.04 * math.sin(2 * math.pi * 0.35 * t)))
    assert not sp.percept.present                         # 1 ม. ไม่นับว่าเข้ามาหาโคม

def test_sensor_dropouts_do_not_lose_the_person():
    """ผู้ใช้: เห็นแล้วหลุดบ่อย -> อัลตร้าโซนิคหาย ("-") เป็นพักๆ ต้องไม่รีเซ็ตหันตรง ไม่หลุดจากคน"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, yaw, log = 0.0, 0.0, 0.0, []
    while t < 40.0:
        L = brain.last
        g = L["packet"].gaze if L else None
        yaw += max(-1.5, min(1.5, ((g[0] * 0.9) if g else 0.0) - yaw))
        a = 0.0 if t < 8.0 else 35.0                               # คนเดินไปด้านข้าง
        d = 0.45 + 0.03 * math.sin(2.2 * t) if abs(yaw - a) < 10.0 else 2.4
        if (t % 1.3) < 0.15:
            d = None                                              # อ่านไม่ได้แวบหนึ่งทุก ~1.3 วิ
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                        "joints": [(yaw, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], yaw))
        t = round(t + 0.05, 4)
    after = [r for r in log if r[0] > 12.0]
    assert all(r[1] in ("Curious", "Engage") for r in after), sorted(set(r[1] for r in after))
    assert abs(log[-1][2] - 35.0) < 12.0, log[-1]


def test_familiar_wall_is_not_a_person_but_a_newcomer_is():
    """ผู้ใช้: เห็นผิด (ผนัง/ของ) -> ของประจำที่ในระยะตรวจจับ + ฐานแกว่งหายใจ: จำได้แล้วไม่สนใจ
    แต่คนที่เดินมายืนหน้าผนังทีหลัง ต้องเห็น"""
    def feed(t):
        yaw = 5.0 * math.sin(2 * math.pi * 0.35 * t)              # ฐานแกว่งตอน Idle
        if t < 90.0:
            d = 0.60 + 0.004 * yaw + 0.008 * math.sin(9.0 * t)    # ของบนโต๊ะ ที่ 0.6 ม. (ในระยะตรวจจับ)
        else:
            d = 0.35 + 0.04 * math.sin(2 * math.pi * 0.35 * t)    # คนยื่นหน้า/มือเข้ามา
        return _tl(t, d, [(yaw, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)])
    log, sp = _sensor_run(100.0, feed)
    late = [r[1] for r in log if 60.0 < r[0] < 90.0]
    assert "Curious" not in late and "Engage" not in late, sorted(set(late))
    assert any(r[1] == "Curious" for r in log if r[0] > 90.0), "คนใหม่หน้าผนังต้องเห็น"


def test_gaze_locks_on_a_hand_and_follows_it_sideways():
    """ผู้ใช้: ตอนสนใจไม่ค่อยตามมือ ส่ายเป็นแพตเทิร์น -> เห็นอยู่ต้องจ้องนิ่ง ; มือเลื่อนไปข้างๆ ต้องตามได้"""
    def hand(t):
        if t < 12.0:
            return 0.0                                          # มือนิ่งตรงหน้า
        return min(30.0, (t - 12.0) * 6.0)                      # ค่อยๆ เลื่อนไปทางซ้าย 6 องศา/วิ จนถึง 30
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, yaw, log = 0.0, 0.0, 0.0, []
    while t < 26.0:
        L = brain.last
        g = L["packet"].gaze if L else None
        yaw += max(-1.5, min(1.5, ((g[0] * 0.9) if g else 0.0) - yaw))
        a = hand(t)
        d = 0.45 + 0.02 * math.sin(3.0 * t) if abs(yaw - a) < 6.0 else 2.4   # มือแคบ: ลำแสง +-6 องศา
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                        "joints": [(yaw, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], yaw))
        t = round(t + 0.05, 4)
    steady = [r[2] for r in log if 6.0 < r[0] < 12.0 and r[1] == "Curious"]
    assert steady and max(abs(y) for y in steady) < 3.0, max(abs(y) for y in steady)   # จ้องนิ่ง ไม่ส่าย
    assert all(r[1] in ("Curious", "Engage") for r in log if r[0] > 6.0)
    assert abs(log[-1][2] - 30.0) < 8.0, log[-1]                                       # ตามมือไปถึง 30


def _hand_body_world(T, hand_at, body_d=0.65, hand_d=0.42, body_sway=0.03):
    """มือ (แคบ +-6 องศา) อยู่หน้าตัวคน (กว้าง +-40 องศา ไกลกว่า) ; หลังจากนั้นเป็นผนัง"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    t, nxt, yaw, log = 0.0, 0.0, 0.0, []
    while t < T:
        L = brain.last
        g = L["packet"].gaze if L else None
        yaw += max(-1.5, min(1.5, ((g[0] * 0.9) if g else 0.0) - yaw))
        a = hand_at(t)
        if a is not None and abs(yaw - a) < 6.0:
            d = hand_d + 0.015 * math.sin(3.0 * t)
        elif abs(yaw) < 40.0:
            d = body_d + body_sway * math.sin(2.2 * t)
        else:
            d = 2.4
        brain.on_frame({"dist_m": d, "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                        "joints": [(yaw, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20), (0, 0, 20)]}, t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], yaw, a))
        t = round(t + 0.05, 4)
    return log


def test_follows_hand_in_front_of_the_body():
    """บั๊กจริงบนหุ่น ("หัน +0" ตลอด): มือเลื่อนออก ลำแสงไปเจอตัวคนข้างหลัง -> ต้องรู้ว่าเป้าหลุด แล้วหันตามมือ"""
    log = _hand_body_world(28.0, lambda t: 0.0 if t < 12.0 else min(30.0, (t - 12.0) * 6.0))
    assert any(r[1] == "Curious" for r in log if r[0] < 12.0)
    errs = sorted(abs(r[2] - r[3]) for r in log if r[0] > 14.0)
    assert errs[len(errs) // 2] < 8.0, errs[len(errs) // 2]        # ส่วนใหญ่ตามทัน
    assert abs(log[-1][2] - 30.0) < 8.0, log[-1]


def test_hand_withdrawn_keeps_watching_the_person():
    """ดึงมือออกไปเลย (ตัวคนยังอยู่) -> หาใกล้ๆ ไม่เจอ แล้วกลับมาจ้องคนที่เดิม ไม่หลุดความสนใจ"""
    log = _hand_body_world(30.0, lambda t: 0.0 if t < 12.0 else None)
    assert all(r[1] in ("Curious", "Engage") for r in log if r[0] > 10.0), sorted(set(r[1] for r in log if r[0] > 10))
    assert abs(log[-1][2]) < 8.0, log[-1]


def test_follows_hand_only_8cm_in_front_of_the_body():
    """นั่งใกล้โคม มือยื่นจากอกไม่ถึงคืบ (ต่างกัน 8 ซม.) ก็ต้องแยกออกและหันตามได้"""
    log = _hand_body_world(28.0, lambda t: 0.0 if t < 12.0 else min(30.0, (t - 12.0) * 6.0),
                           body_d=0.50, hand_d=0.42, body_sway=0.02)   # นั่ง: ตัวโยกน้อย
    assert abs(log[-1][2] - 30.0) < 8.0, log[-1]


def _run_brain(T, feed, setup=None, dt=0.05):
    """รันสมองแบบปรับค่า cfg ได้ ; feed(t, brain) -> tlm ; คืน [(t, state, H)]"""
    from sensor_perception import SensorPerception
    sp = SensorPerception(now=0.0)
    brain = LampBrain(perception=sp, alert=lambda m: None, now=0.0)
    if setup:
        setup(brain)
    t, nxt, log = 0.0, 0.0, []
    while t < T:
        brain.on_frame(feed(t, brain), t)
        if t >= nxt:
            brain.tick(t)
            nxt += 0.1
            log.append((t, brain.last["state"], dict(brain.last["H"]), brain.last))
        t = round(t + dt, 4)
    return log


def test_sickness_overrides_any_emotion():
    """ผู้ใช้: ป่วยสำคัญสุด อบอุ่นหรืออยู่อะไรก็ตาม ป่วยต้องมาก่อน"""
    keys = [(t, "1") for t in range(6, 20, 2)] + [(t, "4") for t in range(46, 70, 3)]
    def feed(t, brain):
        kseq = sum(1 for kt, _ in keys if t >= kt)
        d = 0.45 + 0.04 * math.sin(2 * math.pi * 0.35 * t)
        return {"dist_m": d, "wet": 1.0 if 22.0 <= t < 36.0 else 0.0, "key": keys[kseq - 1][1] if kseq else None,
                "key_seq": kseq, "t_rx": t, "joints": [(0, 0, 20)] * 5}
    log = _run_brain(90.0, feed)
    assert any(r[1] == "Engage" for r in log if r[0] < 22.0)
    t_sick = next(r[0] for r in log if r[1] == "Sick")
    assert 22.0 < t_sick < 36.0, t_sick                              # อบอุ่นอยู่ก็ป่วยมาก่อน
    during = [r[1] for r in log if t_sick < r[0] < 45.0]
    assert set(during) <= {"Sick"}, sorted(set(during))              # ระหว่างป่วย ไม่กลับไปสนใจ/อบอุ่น
    assert log[-1][1] in ("Idle", "Curious", "Engage"), log[-1][1]   # รักษาแล้วหาย กลับมาเป็นปกติ


def test_sick_and_sleepy_sleeps_sick():
    """ง่วงแบบป่วยๆ: ป่วยแล้วไม่มีใคร -> หลับ (บอร์ดยังสั่น/ซีดตอนหลับ จากพารามิเตอร์ความแข็งแรง)"""
    def feed(t, brain):
        return {"dist_m": 2.4, "wet": 1.0 if t < 25.0 else 0.0, "key": None, "key_seq": 0, "t_rx": t,
                "joints": [(0, 0, 20)] * 5}
    log = _run_brain(80.0, feed)
    assert any(r[1] == "Sick" for r in log)
    slept = [r for r in log if r[1] == "Sleep"]
    assert slept and slept[0][3]["params"]["warmth"] < 0.7, slept[0][3]["params"]["warmth"]


def test_sleep_pressure_builds_even_with_company():
    """ผู้ใช้: ตื่นอยู่ความง่วงเพิ่มเรื่อยๆ แม้มีคนสนใจ ครบ 12 ชม. หลับ (ย่อเวลา: 12 ชม. -> 120 วิ)"""
    def setup(brain):
        brain.cfg.awake_full_s = 120.0
    keys = [(t, "1") for t in range(5, 200, 4)]                     # มีคนเล่นด้วยตลอด
    def feed(t, brain):
        kseq = sum(1 for kt, _ in keys if t >= kt)
        return {"dist_m": 0.45 + 0.04 * math.sin(2 * math.pi * 0.35 * t), "wet": 0.0,
                "key": "1" if kseq else None, "key_seq": kseq, "t_rx": t, "joints": [(0, 0, 20)] * 5}
    log = _run_brain(160.0, feed, setup)
    early = [r[2]["sleepiness"] for r in log if 20.0 < r[0] < 30.0]
    late = [r[2]["sleepiness"] for r in log if 100.0 < r[0] < 110.0]
    assert max(late) > max(early) + 0.15, (max(early), max(late))   # ง่วงสะสมทั้งที่มีคนเล่นด้วย
    assert any(r[1] == "Sleep" for r in log if r[0] > 110.0), "ครบ 12 ชม. ต้องหลับแม้มีคน"


def test_fear_beats_curiosity_on_quick_approach():
    """ผู้ใช้: ตอนสนใจ กลัวไม่ค่อยขึ้น อยากให้กลัวสำคัญกว่า -> สนใจอยู่แล้วเข้ามา 0.9 ม./วิ ต้องกลัว"""
    def feed(t):
        d = 0.65 if t < 10.0 else max(0.25, 0.65 - (t - 10.0) * 0.9)
        return _tl(t, d + 0.01 * math.sin(3.0 * t))
    log, _ = _sensor_run(15.0, feed)
    assert any(r[1] == "Curious" for r in log if r[0] < 10.0)
    assert any(r[1] == "Fear" for r in log if r[0] > 10.0)


def test_sickness_makes_sleep_sooner_and_longer():
    """ผู้ใช้: ป่วยแล้วหลับนานขึ้น -> ป่วยหลับเร็วกว่าและนานกว่า (ย่อ 8 นาที -> 60 วิ)"""
    def run(wet):
        def feed(t, brain):
            return {"dist_m": 2.4, "wet": wet if t < 20 else 0.0, "key": None, "key_seq": 0, "t_rx": t,
                    "joints": [(0, 0, 20)] * 5}
        def setup(b):
            b.cfg.sleep_min_s = 60.0
        log = _run_brain(400.0, feed, setup)
        ts = next(r[0] for r in log if r[1] == "Sleep")
        tw = next(r[0] for r in log if r[0] > ts and r[1] != "Sleep")
        return ts, tw - ts
    t_ok, len_ok = run(0.0)
    t_sick, len_sick = run(1.0)
    assert t_sick < t_ok - 5.0, (t_ok, t_sick)
    assert len_sick > len_ok + 20.0, (len_ok, len_sick)


def test_mild_sickness_makes_curiosity_harder():
    """ป่วยไม่ถึงเกณฑ์สถานะป่วย ก็สนใจยากขึ้น"""
    def run(sick):
        def setup(b):
            b.bank.hormones["sickness"].h = sick
        def feed(t, brain):
            return {"dist_m": 0.62 + 0.03 * math.sin(2.2 * t), "wet": 0.0, "key": None, "key_seq": 0, "t_rx": t,
                    "joints": [(0, 0, 20)] * 5}
        log = _run_brain(40.0, feed, setup)
        return next(r[0] for r in log if r[1] == "Curious")
    assert run(0.35) > run(0.0) + 3.0


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    fails = 0
    for n, f in tests:
        try:
            f(); print(f"PASS  {n}")
        except Exception:
            fails += 1; print(f"FAIL  {n}"); traceback.print_exc()
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
