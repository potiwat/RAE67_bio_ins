"""ตัวเชื่อมฝั่งโน้ตบุ๊ก: สมอง (กล้อง + ฮอร์โมน + FSM) -> WiFi/serial -> ESP32
วางไฟล์นี้ไว้ในโฟลเดอร์เดียวกับโค้ดชุดก่อน (behavior.py, vision.py, viewer.py ...)

    pip install pyserial
    ต่อ WiFi ชื่อ lamp-robot (รหัส lamp12345) ก่อน แล้ว
    python host_bridge.py                 # กล้องจริง ผ่าน WiFi
    python host_bridge.py --sim           # คนปลอม ไม่ใช้กล้อง
    python host_bridge.py --dry-run --sim # ไม่ต่อบอร์ด แค่ดูว่าจะส่งอะไร
    python host_bridge.py --serial --port COM5 --warmup 8   # ผ่านสาย USB แทน

ปุ่มในหน้าต่าง: q ออก | r รีเซ็ตฮอร์โมน | b จำลองกล้องเสีย | s เซฟภาพ
"""
import argparse
import time

import link


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--udp", default="192.168.4.1:9000",
                    help="ที่อยู่ของบอร์ดในโหมด WiFi (ค่าเริ่มต้นคือโหมด AP)")
    ap.add_argument("--serial", action="store_true",
                    help="ใช้สาย USB แทน WiFi (ต้องตั้ง LINK_MODE = stdio บนบอร์ดด้วย)")
    ap.add_argument("--port", default=None, help="พอร์ต serial ของ ESP32 (ใช้กับ --serial)")
    ap.add_argument("--baud", type=int, default=115200)   # พอร์ต REPL ของ ESP32 ตายตัวที่ค่านี้
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--face-near", type=float, default=0.55)
    ap.add_argument("--send-hz", type=float, default=50.0)
    ap.add_argument("--warmup", type=float, default=0.0,
                    help="รอกี่วินาทีก่อนเริ่มส่ง (โหมด serial ควรตั้ง 8 เพราะบอร์ดรีบูตตอนเปิดพอร์ต)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="ไม่เปิด serial")
    ap.add_argument("--duration", type=float, default=0.0)
    return ap.parse_args()


class Bridge:
    """ช่องทางคุยกับบอร์ด: WiFi UDP (ค่าเริ่มต้น) หรือสาย USB ; --dry-run = ไม่ต่อจริง"""

    def __init__(self, dry=False, udp=None, serial_port=None, baud=115200):
        self.dry, self.ser, self.sock, self.addr = dry, None, None, None
        self.reader = link.Reader(max_len=64)
        self.last_tlm, self.last_tlm_t = None, -1e9
        self.sent = self.recv = 0
        if dry:
            return
        if serial_port:
            import serial
            self.ser = serial.Serial(serial_port, baud, timeout=0, write_timeout=0.05)
            self.ser.reset_input_buffer()
        else:
            import socket
            host, _, port = udp.partition(":")
            self.addr = (host, int(port or 9000))
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            self.sock.bind(("0.0.0.0", 0))

    def send(self, data):
        self.sent += 1
        try:
            if self.ser is not None:
                self.ser.write(data)
            elif self.sock is not None:
                self.sock.sendto(data, self.addr)
        except Exception as e:
            print("ส่งไม่สำเร็จ:", e)

    def poll(self, now):
        chunks = []
        try:
            if self.ser is not None:
                chunks.append(self.ser.read(4096))
            elif self.sock is not None:
                for _ in range(16):
                    try:
                        data, _addr = self.sock.recvfrom(2048)
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                    if not data:
                        break
                    chunks.append(data)
        except Exception:
            return
        for data in chunks:
            for body in self.reader.feed(data):
                try:
                    self.last_tlm = link.decode_telemetry(body)
                    self.last_tlm_t = now
                    self.recv += 1
                except Exception:
                    pass

    def alive(self, now):
        return (self.ser is not None or self.sock is not None) and (now - self.last_tlm_t) < 1.0

    def close(self):
        if self.ser is not None:
            self.ser.close()
        if self.sock is not None:
            self.sock.close()


FAULT_NAMES = (("estop", 1), ("blocked", 2), ("hot", 4), ("fb_lost", 8),
               ("undervolt", 16), ("host_lost", 32), ("bus_error", 64))


def fault_text(bits):
    return " ".join(n for n, b in FAULT_NAMES if bits & b) or "ok"


def main():
    a = parse()
    if a.serial and not a.dry_run and not a.port:
        raise SystemExit("โหมด --serial ต้องระบุ --port ด้วย")
    from behavior import LampBrain
    from perception import PerceptionConfig, FrameInfo

    brain = LampBrain(speed=a.speed, perception_cfg=PerceptionConfig(face_near_h=a.face_near),
                      now=time.monotonic())
    bridge = Bridge(dry=a.dry_run, udp=None if a.serial else a.udp,
                    serial_port=a.port if a.serial else None, baud=a.baud)
    if not a.dry_run:
        print("ช่องทาง: %s" % ("serial %s" % a.port if a.serial else "UDP %s" % a.udp))
    if a.sim:
        from vision import ScriptedPersonSource
        src, cam, vp = ScriptedPersonSource(t0=time.monotonic()), None, None
    else:
        from vision import Camera, VisionPipeline
        cam, vp, src = Camera(a.camera), VisionPipeline(), None

    viewer = cv2 = None
    if not a.headless:
        import cv2
        import viewer

    seq, fake_fault = 0, False
    warned = [False]
    last_status = [0.0]
    t0 = t_prev = time.monotonic()
    next_tick = next_send = t0
    pkt, frame, info, fps, last_state = None, None, None, 0.0, None
    try:
        while True:
            now = time.monotonic()
            if src is not None:
                frame, info = src.read(now)
                time.sleep(max(0.0, 1 / 30 - (time.monotonic() - now)))
            else:
                ok, frame, t_cap = cam.read()
                info = vp.process(frame, t_cap) if ok else FrameInfo(t=t_cap, ok=False)
            if fake_fault:
                info = FrameInfo(t=info.t, ok=False)
            now = time.monotonic()
            brain.on_frame(info, now)
            while now >= next_tick:
                pkt = brain.tick(now)
                next_tick += brain.cfg.slow_dt
                if now - next_tick > 1.0:
                    next_tick = now

            warm = (now - t0) < a.warmup
            if warm and not warned[0] and now - t0 > 0.5:
                warned[0] = True
                print("รอบอร์ดบูต %.0f วินาทีก่อนเริ่มส่ง..." % a.warmup)
            if pkt is not None and not warm and now >= next_send:     # ส่งถี่กว่ารอบคิด เพื่อไม่ให้ ESP32 มองว่าเงียบ
                next_send = now + 1.0 / a.send_hz
                seq += 1
                bridge.send(link.encode_command(seq, int((now - t0) * 1000),
                                                pkt.mode, pkt.params, pkt.gaze))
            bridge.poll(now)

            dt = now - t_prev
            t_prev = now
            fps += (1.0 / max(dt, 1e-3) - fps) * 0.1
            state = brain.last.get("state") if brain.last else None
            if now - last_status[0] > 3.0:          # รายงานสถานะลิงก์เป็นระยะ ไม่ต้องรอสถานะเปลี่ยน
                last_status[0] = now
                tl0 = bridge.last_tlm
                print("[%7.1fs] link %-4s sent=%d recv=%d  robot=%s  fault=%s" %
                      (now - t0, "OK" if bridge.alive(now) else "--",
                       bridge.sent, bridge.recv,
                       tl0["state"] if tl0 else "-",
                       fault_text(tl0["fault"]) if tl0 else "-"))
            if state != last_state:
                last_state = state
                tl = bridge.last_tlm
                print("[%7.1fs] %-8s robot=%s fault=%s" %
                      (now - t0, state, tl["state"] if tl else "-",
                       fault_text(tl["fault"]) if tl else "-"))

            if not a.headless:
                snap = dict(brain.last, alerts=brain.alerts) if brain.last else None
                tl = bridge.last_tlm
                extra = "link %s  robot=%s  %s" % (
                    "OK" if bridge.alive(now) else ("DRY" if a.dry_run else "LOST"),
                    tl["state"] if tl else "-", fault_text(tl["fault"]) if tl else "-")
                img = viewer.render(frame, info, snap, _LampView(tl), fps, extra)
                cv2.imshow("lamp", img)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("q"):
                    break
                elif k == ord("r"):
                    brain.bank.reset_all()
                elif k == ord("b"):
                    fake_fault = not fake_fault
                elif k == ord("s"):
                    cv2.imwrite("lamp_%d.png" % int(now), img)
            if a.duration and now - t0 >= a.duration:
                break
    finally:
        bridge.close()
        if cam:
            cam.release()
        if not a.headless and cv2 is not None:
            cv2.destroyAllWindows()


class _LampView:
    """ห่อ telemetry ให้หน้าตาเหมือน Lamp ของซิม เพื่อใช้ viewer.py ตัวเดิมวาดมุมจริงของหุ่น"""
    NAMES = ("yaw", "shoulder", "elbow", "head_pitch", "head_roll")

    def __init__(self, tlm):
        self.angles = dict((n, 0.0) for n in self.NAMES)
        self.mode = tlm["state"] if tlm else "Blind"
        self.stale = tlm is None
        self.light = {"rgb": (255, 200, 120), "intensity": 0.6}
        if tlm:
            for i, n in enumerate(self.NAMES):
                self.angles[n] = tlm["joints"][i][0]


if __name__ == "__main__":
    main()
