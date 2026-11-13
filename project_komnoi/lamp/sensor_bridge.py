"""ตัวรันฝั่งโน้ตบุ๊ก (แทนกล้อง): เซนเซอร์บนบอร์ด -> ฮอร์โมน + FSM -> สั่งโคม + บันทึก CSV

    ต่อ WiFi ชื่อ lamp-robot (รหัส lamp12345) ก่อน แล้ว
    python sensor_bridge.py                   # โคมจริง
    python sensor_bridge.py --sim --dry-run   # ไม่ต้องมีบอร์ด: เซนเซอร์จำลองตามสถานการณ์ใน sensor_sim.py
    python sensor_bridge.py --sim             # เซนเซอร์จำลอง แต่สั่งโคมจริง (ดูท่าทางตามเรื่อง)
    python sensor_bridge.py --serial --port COM5   # ผ่านสาย USB แทน WiFi (บอร์ดต้องตั้ง LINK_MODE = "stdio")
                                                   # WiFi โน้ตบุ๊กยังต่ออินเทอร์เน็ตได้ตามปกติ

ตอนหลับ: Sleep~ = หลับตา (ไม่รับรู้ระยะ, รับแค่ปุ่ม 5) ; Sleep* = แอบดู (เงยหน้ามองหาคนทุก 20 วิ)
ระหว่างรัน (Windows) กดคีย์บอร์ดในหน้าต่าง terminal ได้:
    1-9 = กดปุ่มแทน keypad (ใช้ทดสอบตอนยังไม่ได้ต่อ keypad)   r = รีเซ็ตฮอร์โมน   q = ออก
ทุกรอบคิด (10 Hz) บันทึกลง logs/run_*.csv : เซนเซอร์, S, H, โหมด, พารามิเตอร์, สถานะโคม
"""
import argparse
import csv
import os
import time

import link
from host_bridge import Bridge, fault_text
from sensor_perception import HORMONES, KEY_NAMES, SensorPerception

PARAMS = ("tempo", "amp", "lean", "gaze_follow", "brightness", "warmth")
VERSION = "2026-11-11 r19 (กลัวชนะสนใจ, ป่วยหลับเร็ว/นาน/สนใจยาก, แอบดูหน้าตรง)"


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--udp", default="192.168.4.1:9000")
    ap.add_argument("--web-port", type=int, default=8080, help="เว็บแดชบอร์ด (0 = ปิด)")
    ap.add_argument("--web-host", default="127.0.0.1", help="0.0.0.0 = ให้เครื่องอื่นในวงเดียวกันเปิดดูได้")
    ap.add_argument("--no-browser", action="store_true", help="ไม่ต้องเปิดเบราว์เซอร์ให้อัตโนมัติ")
    ap.add_argument("--day-hours", type=float, default=12.0,
                    help="ตื่นนานเท่านี้ (ชม.) ความง่วงสะสมเต็มแล้วหลับแม้มีคน ; สาธิตใช้ค่าน้อยเช่น 0.05 (= 3 นาที)")
    ap.add_argument("--serial", action="store_true", help="ใช้สาย USB แทน WiFi (บอร์ด LINK_MODE = stdio)")
    ap.add_argument("--port", default=None, help="พอร์ต USB ของบอร์ด เช่น COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--warmup", type=float, default=None,
                    help="รอบอร์ดบูตกี่วินาทีก่อนเริ่มสั่ง (โหมด serial ค่าเริ่มต้น 8: เปิดพอร์ตแล้วบอร์ดรีเซ็ต)")
    ap.add_argument("--sim", action="store_true", help="ใช้เซนเซอร์จำลองแทนค่าจากบอร์ด")
    ap.add_argument("--dry-run", action="store_true", help="ไม่ต่อบอร์ด")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--send-hz", type=float, default=50.0)
    ap.add_argument("--duration", type=float, default=0.0)
    ap.add_argument("--log", default=None, help="ไฟล์ CSV (ค่าเริ่มต้น logs/run_<เวลา>.csv) ; none = ไม่บันทึก")
    ap.add_argument("--quiet", action="store_true", help="ไม่พิมพ์สถานะทุกวินาที")
    return ap.parse_args()


class _Keys:
    """อ่านคีย์บอร์ดแบบไม่รอ (Windows) ; ระบบอื่นไม่มีผล"""

    def __init__(self):
        try:
            import msvcrt
            self.m = msvcrt
        except ImportError:
            self.m = None

    def get(self):
        if self.m is None or not self.m.kbhit():
            return None
        try:
            return self.m.getwch()
        except Exception:
            return None


def _fmt(v, f="%.2f"):
    return "  -  " if v is None else f % v


def main():
    a = parse()
    from behavior import LampBrain

    print("สมองโคม เวอร์ชัน", VERSION)
    t0 = time.monotonic()
    sp = SensorPerception(speed=a.speed, now=t0)
    brain = LampBrain(speed=a.speed, perception=sp, now=t0)
    brain.cfg.awake_full_s = a.day_hours * 3600.0
    if a.serial and not a.dry_run and not a.port:
        raise SystemExit("โหมด --serial ต้องระบุ --port ด้วย เช่น --port COM5")
    warmup = a.warmup if a.warmup is not None else (8.0 if a.serial else 0.0)
    bridge = Bridge(dry=a.dry_run, udp=None if a.serial else a.udp,
                    serial_port=a.port if a.serial else None, baud=a.baud)
    sim = None
    if a.sim:
        from sensor_sim import ScriptedSensors
        sim = ScriptedSensors(t0, speed=a.speed)
        print("เซนเซอร์จำลอง: ดูเรื่องราวใน sensor_sim.py (วนทุก 110 วินาที)")
    if not a.dry_run:
        if a.serial:
            print("ช่องทาง: USB %s -- รอบอร์ดบูต %.0f วินาที (ปิด mpremote/REPL ก่อน ไม่งั้นพอร์ตไม่ว่าง)" % (a.port, warmup))
        else:
            print("ช่องทาง: UDP %s (ต่อ WiFi lamp-robot แล้วหรือยัง?)" % a.udp)

    writer = logf = None
    if (a.log or "").lower() != "none":
        path = a.log or os.path.join("logs", time.strftime("run_%Y%m%d_%H%M%S.csv"))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        logf = open(path, "w", newline="", encoding="utf-8")
        writer = csv.writer(logf)
        writer.writerow(["t", "dist_m", "wet", "key", "valid", "present"]
                        + ["S_" + h for h in HORMONES] + ["S_care"]
                        + ["H_" + h for h in HORMONES] + ["state", "peek"] + list(PARAMS)
                        + ["robot_state", "robot_fault", "link"])
        print("บันทึกลง", path)

    web = None
    if a.web_port:
        from web_ui import WebUI
        web = WebUI(a.web_host, a.web_port)
        url = web.start()
        if url:
            print("เว็บแดชบอร์ด:", url)
            if not a.no_browser:
                try:
                    import webbrowser
                    webbrowser.open(url)
                except Exception:
                    pass
        else:
            web = None

    keys = _Keys()
    last_rx = -1
    seq = 0
    pkt = None
    next_tick = next_send = t0
    last_print = 0.0
    last_state = None
    press_shown = 0
    ignored_shown = 0
    last_peek = False
    try:
        while True:
            now = time.monotonic()
            bridge.poll(now)
            if sim is not None:
                brain.on_frame(sim.read(now), now)
            elif bridge.recv != last_rx and bridge.last_tlm is not None:
                last_rx = bridge.recv
                tl = dict(bridge.last_tlm, t_rx=bridge.last_tlm_t)
                brain.on_frame(tl, now)
            else:
                brain.on_frame(None, now)           # ไม่มีข้อมูลใหม่ -> ตัวรับรู้เช็คความสดเอง

            k = keys.get()
            if k in KEY_NAMES:
                sp.press(k, now)
            elif k == "r":
                brain.bank.reset_all()
                print("รีเซ็ตฮอร์โมนแล้ว")
            elif k == "q":
                break
            for cmd, arg in (web.commands() if web is not None else ()):
                if cmd == "key" and arg in KEY_NAMES:      # ปุ่มบนเว็บ = กดปุ่มจริง
                    sp.press(arg, now)
                elif cmd == "dip":
                    sp.simulate_wet(now, 12.0)
                    print("[%7.1fs] จำลองจุ่มน้ำ 12 วิ (จากเว็บ)" % (now - t0))
                elif cmd == "reset":
                    brain.bank.reset_all()
                    print("[%7.1fs] รีเซ็ตฮอร์โมน (จากเว็บ)" % (now - t0))

            while now >= next_tick:
                pkt = brain.tick(now)
                next_tick += brain.cfg.slow_dt
                if now - next_tick > 1.0:
                    next_tick = now
                L = brain.last
                tl = bridge.last_tlm
                if web is not None:
                    lk = sp.presses[-1] if sp.presses and now - sp.presses[-1][0] < 4.0 else None
                    web.push(now - t0, {
                        "t": now - t0, "version": VERSION, "state": L["state"], "peek": bool(L.get("peek")),
                        "searching": bool(L.get("searching")), "gaze_yaw": L.get("gaze_yaw", 0.0),
                        "in_state": (now - brain.fsm.since) * a.speed,
                        "dist": sp.dist, "wet": sp.wet, "fake_wet": now < sp.fake_wet_until,
                        "H": {h: L["H"][h] for h in HORMONES},
                        "last_key": lk[1] if lk else None,
                        "link": bridge.alive(now), "dry": bool(a.dry_run), "logging": writer is not None,
                        "robot": tl["state"] if tl else None,
                        "awake_h": L.get("awake_h"), "pressure": L.get("pressure"),
                    })
                if writer is not None:
                    p = L["percept"]
                    lk = sp.presses[-1][1] if sp.presses and now - sp.presses[-1][0] < 0.15 else ""
                    writer.writerow(["%.2f" % (now - t0), _fmt(sp.dist, "%.3f").strip(),
                                     _fmt(sp.wet).strip(), lk, int(p.valid), int(p.present)]
                                    + ["" if L["S"].get(h) is None else "%.3f" % L["S"][h]
                                       for h in HORMONES + ("care",)]
                                    + ["%.3f" % L["H"][h] for h in HORMONES]
                                    + [L["state"], int(bool(L.get("peek")))]
                                    + ["%.3f" % L["params"][n] for n in PARAMS]
                                    + [tl["state"] if tl else "", tl["fault"] if tl else "",
                                       int(bridge.alive(now))])

            if pkt is not None and now >= next_send and now - t0 >= warmup:
                next_send = now + 1.0 / a.send_hz
                seq += 1
                bridge.send(link.encode_command(seq, int((now - t0) * 1000),
                                                pkt.mode, pkt.params, pkt.gaze))

            while press_shown < len(sp.presses):
                tp, key = sp.presses[press_shown]
                press_shown += 1
                print("[%7.1fs] ปุ่ม %s %s" % (tp - t0, key, KEY_NAMES.get(key, "")))
            if len(sp.ignored_presses) < ignored_shown:
                ignored_shown = 0
            while ignored_shown < len(sp.ignored_presses):
                tp, key = sp.ignored_presses[ignored_shown]
                ignored_shown += 1
                print("[%7.1fs] ปุ่ม %s -- ไม่สนใจ (หลับอยู่ ปลุกด้วยปุ่ม 5)" % (tp - t0, key))
            peek = bool(brain.last.get("peek")) if brain.last else False
            if peek != last_peek:
                last_peek = peek
                print("[%7.1fs] >>> %s" % (now - t0, "แอบดู (เงยหน้ามองหาคน)" if peek else "ก้มหลับต่อ"))
            state = brain.last.get("state") if brain.last else None
            if state != last_state:
                last_state = state
                print("[%7.1fs] >>> %s" % (now - t0, state))
            if not a.quiet and now - last_print >= 1.0 and brain.last:
                last_print = now
                H = brain.last["H"]
                tl = bridge.last_tlm
                label = ("Sleep*" if peek else "Sleep~") if state == "Sleep" else state
                L = brain.last
                look = (" หัน %+3.0f%s" % (L.get("gaze_yaw", 0.0), " กวาดหา" if L.get("searching") else "")
                        if state in ("Curious", "Engage") else "")
                print("[%7.1fs] %-7s ระยะ %s ชื้น %s%s | cau %.2f cur %.2f aff %.2f slp %.2f sick %.2f | link %s robot=%s %s"
                      % (now - t0, label, _fmt(sp.dist), _fmt(sp.wet), look,
                         H["caution"], H["curiosity"], H["affinity"], H["sleepiness"], H["sickness"],
                         "OK" if bridge.alive(now) else ("DRY" if a.dry_run else "--"),
                         tl["state"] if tl else "-", fault_text(tl["fault"]) if tl else "-"))
            if a.duration and now - t0 >= a.duration:
                break
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        if web is not None:
            web.close()
        if logf is not None:
            logf.close()
            print("ปิดไฟล์ log แล้ว")


if __name__ == "__main__":
    main()
