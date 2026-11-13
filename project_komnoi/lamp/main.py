"""โคมที่ตอบสนองต่อคนผ่านกล้อง

  pip install -r requirements.txt
  python main.py                 # ใช้กล้องจริง (index 0)
  python main.py --sim           # ไม่มีกล้อง: ใช้คนปลอมเดินผ่าน/เข้าใกล้/พุ่งเข้าหา
  python main.py --speed 3       # เร่งเวลาของฮอร์โมน 3 เท่า (ลองเล่นเร็วขึ้น)
  python main.py --face-near 0.4 # ตกใจง่ายขึ้น (ใบหน้าสูง 40% ของภาพก็นับว่า "ใกล้มาก")
  python test_lamp.py            # รันชุดทดสอบ

ปุ่มลัดในหน้าต่าง
  q  ออก          r  รีเซ็ตฮอร์โมนทั้งหมด
  b  จำลองกล้องเสีย (ดูโหมด Blind + safe fallback)    s  เซฟภาพหน้าจอ
"""
import argparse
import time

import cv2

from behavior import LampBrain, BrainConfig
from lamp import Lamp
from perception import PerceptionConfig, FrameInfo
import viewer


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0, help="index ของกล้อง")
    ap.add_argument("--sim", action="store_true", help="ใช้คนปลอมแทนกล้อง (ไม่ต้องมีกล้อง)")
    ap.add_argument("--speed", type=float, default=1.0, help="เร่ง/หน่วงเวลาของฮอร์โมน (3 = เร็วขึ้น 3 เท่า)")
    ap.add_argument("--headless", action="store_true", help="ไม่เปิดหน้าต่าง พิมพ์ log อย่างเดียว")
    ap.add_argument("--duration", type=float, default=0.0, help="รันกี่วินาทีแล้วออก (0 = ไม่จำกัด)")
    ap.add_argument("--face-near", type=float, default=0.55,
                    help="ความสูงใบหน้า/ภาพ ที่นับว่า 'ใกล้มาก' (ลดค่าถ้าอยากให้ตกใจง่ายขึ้น)")
    ap.add_argument("--dshow", action="store_true", help="Windows: เปิดกล้องด้วย DirectShow (เปิดเร็วกว่าในกล้องบางรุ่น)")
    ap.add_argument("--frozen-after", type=float, default=3.0, help="ภาพเหมือนเดิมเป๊ะนานกี่วินาทีถึงนับว่ากล้องค้าง (0 = ปิด)")
    ap.add_argument("--no-motion", action="store_true", help="ปิดตัวตรวจจับการเคลื่อนไหว (ใช้แต่ใบหน้า)")
    return ap.parse_args()


def main():
    a = parse()
    pcfg = PerceptionConfig(face_near_h=a.face_near)
    brain = LampBrain(speed=a.speed, perception_cfg=pcfg, now=time.monotonic())
    lamp = Lamp()
    if a.sim:
        from vision import ScriptedPersonSource
        src, cam, vp = ScriptedPersonSource(t0=time.monotonic()), None, None
    else:
        from vision import Camera, VisionPipeline
        cam, vp, src = Camera(a.camera, dshow=a.dshow), VisionPipeline(use_motion=not a.no_motion,
                                           frozen_after_s=a.frozen_after or None), None

    fake_fault = False
    t_prev = time.monotonic()
    next_tick = t_prev
    t_start, fps, last_print, last_state = t_prev, 0.0, 0.0, None
    pkt, frame, info = None, None, None
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
        while now >= next_tick:                   # slow loop 10 Hz
            pkt = brain.tick(now)
            next_tick += brain.cfg.slow_dt
            if now - next_tick > 1.0:
                next_tick = now
        dt = now - t_prev
        t_prev = now
        fps += (1.0 / max(dt, 1e-3) - fps) * 0.1
        lamp.step(dt, now, pkt)

        snap = dict(brain.last, alerts=brain.alerts) if brain.last else None
        if brain.last and brain.last["state"] != last_state:
            last_state = brain.last["state"]
            H = brain.last["H"]
            print(f"[{now - t_start:7.1f}s] state={last_state:8s} " + " ".join(f"{k[:4]}={v:.2f}" for k, v in H.items()))
        if not a.headless:
            img = viewer.render(frame, info, snap, lamp, fps, "FAULT SIM ON" if fake_fault else None)
            cv2.imshow("lamp", img)
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            elif k == ord("r"):
                brain.bank.reset_all()
            elif k == ord("b"):
                fake_fault = not fake_fault
            elif k == ord("s"):
                cv2.imwrite(f"lamp_{int(now)}.png", img)
        if a.duration and now - t_start >= a.duration:
            break
    if cam:
        cam.release()
    if not a.headless:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
