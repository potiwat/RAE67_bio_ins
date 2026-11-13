"""เล่นท่าทุกอารมณ์ผ่านลูปหลักตัวจริง (ไม่ต้องต่อโน้ตบุ๊ก) -- รันบน REPL:  import tools.poses
ต้องเปิดไฟเซอร์โว ; มือจับสวิตช์ไว้ ; Ctrl-C หยุด (แรงบิดจะปลด -> ประคองแขนก่อนกด)

แกล้งเป็นโน้ตบุ๊กส่งคำสั่งโหมดเข้า Robot.ingest -> ผ่าน safety / slew-rate / SMOOTH_MODE เหมือนใช้งานจริง
วน: Idle -> Curious -> Engage -> Fear -> Sleep -> Idle ... ท่าละ HOLD_S วินาที
ดู 2 อย่าง: ขยับลื่นไหม (ตอนเปลี่ยนท่า) และแต่ละท่าดูออกไหมว่าเป็นอารมณ์อะไร
"""
import time

import config as cfg
import link
import main
import robot as robot_mod

HOLD_S = 6.0
ORDER = (("Idle", "ยืนปกติ ทรง Z"), ("Curious", "สนใจ โน้มเข้าหา"), ("Engage", "เข้าใกล้ อบอุ่น"),
         ("Fear", "ตกใจ ถอยหลบ"), ("Sleep", "ง่วง ห้อยหัว"))
PARAMS = {"tempo": 1.0, "amp": 1.0, "lean": 0.0, "gaze_follow": 0.0, "brightness": 0.8, "warmth": 1.0}


def run(rounds=2):
    bus, light, estop = main.build()
    now = time.ticks_ms() / 1000.0
    bot = robot_mod.Robot(bus, light=light, estop=estop, now=now, log=print)
    found = bot.start(now)
    print("เซอร์โวที่ตอบ:", sorted(found.keys()))
    period_ms = int(1000.0 / cfg.FAST_HZ)
    seq = 0
    t_prev = next_ms = time.ticks_ms()
    t_start = t_prev
    loops = over = 0
    try:
        for r in range(rounds):
            for mode, desc in ORDER:
                print("\n>>> %-8s %s" % (mode, desc))
                t_mode = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), t_mode) < HOLD_S * 1000:
                    now_ms = time.ticks_ms()
                    dt = time.ticks_diff(now_ms, t_prev) / 1000.0
                    t_prev = now_ms
                    if dt <= 0 or dt > 0.25:
                        dt = period_ms / 1000.0
                    now = now_ms / 1000.0
                    seq = (seq + 1) & 0xFFFF
                    bot.ingest(link.encode_command(seq, time.ticks_diff(now_ms, t_start),
                                                   mode, PARAMS, None), now)
                    bot.step(dt, now)
                    bot.telemetry(now)                 # เดินนาฬิกา telemetry ด้วย (ไม่ส่งที่ไหน) ไฟจะได้อัปเดต
                    loops += 1
                    next_ms = time.ticks_add(next_ms, period_ms)
                    d = time.ticks_diff(next_ms, time.ticks_ms())
                    if d > 0:
                        time.sleep_ms(d)
                    else:
                        over += 1
                        next_ms = time.ticks_ms()
                if bot.mode != mode:
                    print("    (โคมอยู่โหมด %s แทน -- fault=%d)" % (bot.mode, bot.fault))
        print("\nจบ -- ตามไม่ทัน %d/%d รอบ ; กลับท่า Idle ค้างไว้" % (over, loops))
        t_end = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t_end) < 3000:
            now_ms = time.ticks_ms()
            seq = (seq + 1) & 0xFFFF
            bot.ingest(link.encode_command(seq, 0, "Idle", PARAMS, None), now_ms / 1000.0)
            bot.step(period_ms / 1000.0, now_ms / 1000.0)
            time.sleep_ms(period_ms)
        print("ค้างท่า Idle (แรงบิดยังอยู่) -- ประคองแขนก่อนปิดไฟ หรือกด Ctrl-D")
    except KeyboardInterrupt:
        print("\nหยุด -- ปลดแรงบิด")
        bot.stop()


run()
