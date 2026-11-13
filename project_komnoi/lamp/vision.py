"""ส่วนที่แตะ OpenCV: กล้อง, ตัวตรวจจับคน, และ "คนปลอม" ไว้ทดสอบโดยไม่ต้องมีกล้อง

ตัวตรวจจับ 2 ตัวทำงานร่วมกัน
  FaceDetector   : Haar cascade หาใบหน้าตรง (แม่นเรื่องระยะ/การหันหน้ามา แต่เห็นเฉพาะคนหันหน้าเข้ากล้อง)
  MotionDetector : background subtraction หาตัวคนที่กำลังเคลื่อนไหว (จับคนเดินผ่านด้านข้างได้)
อยากได้ตัวตรวจจับที่ดีกว่านี้ (YOLO, MediaPipe) แค่เขียนคลาสที่คืน list ของ Detection แล้วเสียบแทนได้
"""
import math
import time

import cv2
import numpy as np

from perception import Detection, FrameInfo


class FaceDetector:
    def __init__(self, work_width=320):
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.cc = cv2.CascadeClassifier(path)
        if self.cc.empty():
            raise RuntimeError("โหลด Haar cascade ไม่ได้ (ต้องใช้ opencv-python 4.x ไม่ใช่ 5.x)")
        self.work_width = work_width

    def detect(self, gray):
        h, w = gray.shape
        s = self.work_width / w
        small = cv2.resize(gray, (self.work_width, int(h * s)), interpolation=cv2.INTER_AREA)
        small = cv2.equalizeHist(small)
        H, W = small.shape
        faces = self.cc.detectMultiScale(small, scaleFactor=1.12, minNeighbors=5,
                                         minSize=(max(20, int(0.08 * H)), max(20, int(0.08 * H))))
        return [Detection(float((x + fw / 2) / W), float((y + fh / 2) / H), float(fh / H), "face")
                for (x, y, fw, fh) in faces]


class MotionDetector:
    def __init__(self, work_width=160, min_area=0.02, warmup_frames=30, lr=0.003):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=36, detectShadows=False)
        self.work_width, self.min_area, self.warmup, self.lr = work_width, min_area, warmup_frames, lr
        self.n = 0
        self.k_open = np.ones((3, 3), np.uint8)
        self.k_close = np.ones((9, 9), np.uint8)
        self.fg_ratio = 0.0
        self.mask = None

    def detect(self, gray):
        h, w = gray.shape
        s = self.work_width / w
        small = cv2.resize(gray, (self.work_width, int(h * s)), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (5, 5), 0)
        fg = self.bg.apply(small, learningRate=self.lr)
        self.n += 1
        if self.n < self.warmup:
            return []
        fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)[1]
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, self.k_open)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, self.k_close)
        self.mask = fg
        H, W = fg.shape
        self.fg_ratio = float(fg.mean()) / 255.0
        if self.fg_ratio > 0.5:                 # ทั้งภาพเปลี่ยน = แสง/กล้องสั่น ไม่ใช่คน
            return []
        cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [cv2.boundingRect(c) for c in cnts if cv2.contourArea(c) >= self.min_area * W * H / 3]
        if not boxes:
            return []
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
        if sum(b[2] * b[3] for b in boxes) < self.min_area * W * H:
            return []
        return [Detection((x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (y1 - y0) / H, "body")]


class VisionPipeline:
    def __init__(self, use_face=True, use_motion=True, frozen_after_s=3.0):   # None = ปิดการตรวจภาพค้าง
        self.face = FaceDetector() if use_face else None
        self.motion = MotionDetector() if use_motion else None
        self.frozen_after_s = frozen_after_s
        self._thumb, self._same_since = None, None

    def process(self, frame_bgr, t):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean()) / 255.0
        thumb = cv2.resize(gray, (32, 24), interpolation=cv2.INTER_AREA)       # ตรวจภาพค้าง (กล้องแฮงก์)
        if self._thumb is not None and brightness > 0.02 and np.array_equal(thumb, self._thumb):
            self._same_since = self._same_since if self._same_since is not None else t
        else:
            self._same_since = None
        self._thumb = thumb
        frozen = (self.frozen_after_s is not None and self._same_since is not None
                  and (t - self._same_since) > self.frozen_after_s)

        dets = []
        if self.face:
            dets += self.face.detect(gray)
        if self.motion:
            dets += self.motion.detect(gray)
        return FrameInfo(t=t, ok=True, brightness=brightness, detections=dets, frozen=frozen)


class Camera:
    def __init__(self, index=0, width=640, height=480, dshow=False):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if dshow else cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(f"เปิดกล้อง index {index} ไม่ได้ (ลอง --camera 1 หรือใช้ --sim)")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self):
        ok, frame = self.cap.read()
        return ok, (frame if ok else None), time.monotonic()

    def release(self):
        self.cap.release()


# ================================================================ คนปลอม (ไว้ทดสอบ/ดูเดโมโดยไม่ต้องมีกล้อง)
def default_scenario(t):
    """คืน list ของ Detection ที่เวลา t วินาที"""
    if 6 <= t < 10:       # เดินผ่านไกลๆ จากซ้ายไปขวา
        return [Detection(0.1 + 0.8 * (t - 6) / 4, 0.55, 0.45, "body")]
    if 14 <= t < 41:      # เดินเข้ามา แล้วยืนระยะกลางหันหน้าเข้าหา
        k = min(1.0, (t - 14) / 6)
        return [Detection(0.5 + 0.02 * math.sin(t * 1.7), 0.45, 0.07 + 0.12 * k, "face")]
    if 41 <= t < 42.2:    # พุ่งเข้าหากล้องเร็วๆ
        k = (t - 41) / 1.2
        return [Detection(0.5, 0.5, 0.19 + 0.34 * k, "face")]
    if 42.2 <= t < 45:
        return [Detection(0.5, 0.5, 0.53, "face")]
    if 45 <= t < 47:      # ถอยออกไป
        k = (t - 45) / 2
        return [Detection(0.5 + 0.3 * k, 0.5, 0.53 - 0.4 * k, "face")]
    if 56 <= t < 60:      # เดินผ่านอีกรอบ (ควรสนใจน้อยลง เพราะเริ่มชิน)
        return [Detection(0.9 - 0.8 * (t - 56) / 4, 0.55, 0.45, "body")]
    return []


class ScriptedPersonSource:
    """แทนกล้อง: สร้างภาพปลอมง่ายๆ + Detection จาก scenario(t)"""
    def __init__(self, scenario=default_scenario, width=640, height=480, t0=0.0):
        self.scenario, self.w, self.h, self.t0 = scenario, width, height, t0

    def read(self, t):
        dets = self.scenario(t - self.t0)
        img = np.full((self.h, self.w, 3), 38, np.uint8)
        for d in dets:
            cx, cy = int(d.cx * self.w), int(d.cy * self.h)
            hh = int(d.h * self.h)
            if d.kind == "face":
                cv2.ellipse(img, (cx, cy), (int(hh * 0.4), int(hh * 0.5)), 0, 0, 360, (150, 170, 220), -1)
                cv2.rectangle(img, (cx - int(hh * 0.9), cy + int(hh * 0.5)), (cx + int(hh * 0.9), self.h),
                              (90, 100, 130), -1)
            else:
                cv2.rectangle(img, (cx - int(hh * 0.18), cy - hh // 2), (cx + int(hh * 0.18), cy + hh // 2),
                              (110, 120, 150), -1)
        return img, FrameInfo(t=t, ok=True, brightness=0.45, detections=dets)
