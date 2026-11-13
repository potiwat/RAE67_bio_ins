"""เทียบโหมดความนุ่มนวล (SMOOTH_MODE) บนหุ่นจริง -- รันบน REPL:  import tools.smooth
ต้องเปิดไฟเซอร์โว ; มือจับสวิตช์ไว้ ; ข้อต่ออื่นค้างท่าปัจจุบันไว้ (ประคองแขนก่อนเริ่ม)

หมุน yaw ไปมา +-20 องศา (คลื่นไซน์ 0.3 Hz) โหมดละ 6 วินาที: off -> speed -> time
วัด: "หยุดกลางทาง" = จำนวนรอบที่สั่งให้ขยับแต่ yaw ไม่ขยับเลย (ยิ่งน้อยยิ่งลื่น)
     "สะดุด" = ความไม่สม่ำเสมอของความเร็ว (ยิ่งน้อยยิ่งนุ่ม)
     "ตามหลัง" = ห่างจากคำสั่งเฉลี่ย (องศา) -- มากไปแปลว่าโหมดนั้นช้าเกิน
ดูด้วยตาด้วยว่าโหมดไหนลื่นสุด แล้วบอก Claude
"""
import math
import time

import config as cfg
from machine import UART, Pin
from scs import SCSBus
from joints import JOINT_BY_NAME, NAMES

AMP = 20.0
FREQ = 0.3
SECONDS = 6.0
MODES = ("off", "speed", "time")

_uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
_dir = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
bus = SCSBus(_uart, dir_pin=_dir, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)


def _fb(sid):
    for _ in range(2):
        try:
            f = bus.feedback(sid)
            if f is not None:
                return f
        except Exception:
            pass
    return None


def run():
    yaw = JOINT_BY_NAME["yaw"]
    period = 1.0 / cfg.FAST_HZ
    print("=" * 56 + "\n เทียบโหมดความนุ่มนวล (yaw +-%d องศา)\n" % AMP + "=" * 56)
    hold = []
    for n in NAMES:                                   # ค้างทุกข้อต่อไว้ที่ท่าปัจจุบัน
        j = JOINT_BY_NAME[n]
        f = _fb(j.sid)
        if f is None:
            print("  %s (ID %d) อ่านค่าไม่ได้ -- หยุด" % (n, j.sid))
            return
        if n != "yaw":
            hold.append((j.sid, f["tick"], 60, 0))
        bus.torque(j.sid, True)
    bus.sync_write_positions(hold + [(yaw.sid, yaw.center_tick, 60, 0)])
    print("  ไป yaw = 0 ช้าๆ ...")
    time.sleep_ms(2500)
    results = []
    try:
        for mode in MODES:
            print("\n  โหมด \"%s\" ..." % mode)
            stalls = moving = 0
            err_sum = 0.0
            jerk = 0.0
            last_meas = last_cmd = last_v = None
            loop_ms = []
            t0 = time.ticks_ms()
            next_ms = t0
            while True:
                now = time.ticks_ms()
                t = time.ticks_diff(now, t0) / 1000.0
                if t >= SECONDS:
                    break
                deg = AMP * math.sin(2 * math.pi * FREQ * t)
                tick = yaw.deg_to_tick(deg)
                if mode == "speed" and last_cmd is not None:
                    v = int(abs(tick - last_cmd) / period * 1.3) + 1
                    item = (yaw.sid, tick, max(20, min(yaw.goal_speed(), v)), 0)
                elif mode == "time":
                    item = (yaw.sid, tick, 0, int(period * 1500))
                else:
                    item = (yaw.sid, tick, yaw.goal_speed(), 0)
                bus.sync_write_positions(hold + [item])
                f = _fb(yaw.sid)
                if f is not None and t > 0.5:
                    m = f["tick"]
                    err_sum += abs(yaw.tick_to_deg(m) - deg)
                    if last_meas is not None and last_cmd is not None:
                        if abs(tick - last_cmd) >= 1:
                            moving += 1
                            if m == last_meas:
                                stalls += 1
                        v = m - last_meas
                        if last_v is not None:
                            jerk += abs(v - last_v)
                        last_v = v
                    last_meas = m
                last_cmd = tick
                next_ms = time.ticks_add(next_ms, int(period * 1000))
                d = time.ticks_diff(next_ms, time.ticks_ms())
                loop_ms.append(time.ticks_diff(time.ticks_ms(), now))
                if d > 0:
                    time.sleep_ms(d)
                else:
                    next_ms = time.ticks_ms()
            n = max(1, moving)
            r = (mode, 100 * stalls // n, jerk / n, err_sum / max(1, len(loop_ms)),
                 sum(loop_ms) / max(1, len(loop_ms)))
            results.append(r)
            print("    หยุดกลางทาง %d%%  สะดุด %.2f  ตามหลัง %.1f องศา  (รอบละ %.1f ms)" % r[1:])
            bus.sync_write_positions(hold + [(yaw.sid, yaw.center_tick, 60, 0)])
            time.sleep_ms(1500)
    except KeyboardInterrupt:
        print("  หยุดกลางคัน")
    print("\n" + "=" * 56 + "\n สรุป (หยุดกลางทาง / สะดุด ยิ่งน้อยยิ่งดี)\n" + "=" * 56)
    for r in results:
        print("  %-6s หยุด %3d%%  สะดุด %.2f  ตามหลัง %.1f" % r[:4])
    print(" ข้อต่อยังค้างแรงอยู่ -- ประคองแขนก่อนปิดไฟ")


run()
