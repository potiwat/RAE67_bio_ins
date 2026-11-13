"""วัดว่าบอร์ดวิ่งได้กี่ Hz จริง -- รันบน REPL:  import tools.bench
MicroPython ช้ากว่า CPython มาก และ GC หยุดชั่วคราวได้ ต้องวัดบนบอร์ดจริงเท่านั้น
ถ้าได้ต่ำกว่า ~60 Hz ให้ลด FAST_HZ ใน config.py หรือลด FEEDBACK_HZ
"""
import gc
import time

import config as cfg
from motion import MotionEngine
from joints import NAMES
from safety import ActuatorSafety
from tools.scan import make_bus

P = {"tempo": 1.0, "amp": 1.0, "lean": 0.2, "gaze_follow": 0.8,
     "brightness": 0.8, "warmth": 0.5}


def bench(n=300):
    m = MotionEngine(dict((k, 0.0) for k in NAMES))
    sf = ActuatorSafety()
    for k in NAMES:
        sf.states[k].meas = 0.0
    dt = 1.0 / cfg.FAST_HZ
    gc.collect()
    t0 = time.ticks_us()
    for i in range(n):
        tg = m.step(dt, "Engage", P, (10.0, -5.0))
        for k in NAMES:
            sf.filter(k, tg[k], dt, i * dt)
        sf.tick_items()
    us = time.ticks_diff(time.ticks_us(), t0) / n
    print("motion+safety: %.0f us/รอบ -> เพดาน %.0f Hz" % (us, 1000000.0 / us))
    return us


def bench_bus(n=100):
    bus = make_bus()
    items = [(j, 500, 400) for j in range(1, 6)]
    t0 = time.ticks_us()
    for _ in range(n):
        bus.sync_write_positions(items)
    us = time.ticks_diff(time.ticks_us(), t0) / n
    print("sync write 5 ตัว: %.0f us/ครั้ง" % us)
    t0 = time.ticks_us()
    for _ in range(n):
        bus.feedback(1)
    us2 = time.ticks_diff(time.ticks_us(), t0) / n
    print("feedback 1 ตัว:   %.0f us/ครั้ง (สำเร็จ %d พลาด %d)" % (us2, bus.ok, bus.errors))
    return us + us2


def run():
    a = bench()
    b = bench_bus()
    total = a + b
    print("\nรวม ~%.0f us/รอบ -> วิ่งได้ประมาณ %.0f Hz" % (total, 1000000.0 / total))
    print("ตั้ง FAST_HZ ไม่เกินประมาณ 70%% ของค่านี้ เผื่อ GC และงานอื่น")


run()
