"""lamp_camera.py - the robot's camera on the laptop + the GUI (pretrained models only, nothing to train)

  person + objects : Ultralytics YOLO11n (COCO 80 classes - use things it knows: cup, bottle, phone, teddy bear, ball)
  hands            : MediaPipe Hand Landmarker                      (all pretrained, nothing to train)
  object identity  : ByteTrack (comes with ultralytics) follows each box. A NEW object is first CONFIRMED (its class
                     voted over LOCK_FRAMES frames) and then its class is LOCKED for as long as that object is tracked
                     -> one physical thing never flips id (bottle <-> remote) and the boredom can build up.
  (YOLO-World was tried for a plain box: found it in 1 of 580 frames -> dropped)
  wave             : an OPEN hand (>= 3 fingers straight) going left-right-left, near a person
  -> per frame:  CAM,<seq>,<person>,<object>,<object_id>,<x>,<y>      (x -1 left..+1 right, y -1 top..+1 bottom)
  -> on a wave:  WAVE,<seq>,<x>

TEST MODE (no robot):   .venv/bin/python lamp_camera.py                 nothing is sent, GUI shows the camera only
WITH THE ESP32:         .venv/bin/python lamp_camera.py --port /dev/cu.usbserial-0001
    the program OWNS the ESP32 USB port (it is the serial monitor too): the GUI shows the ESP32, the terminal also
    accepts typed commands. NOTE: opening the port MAY restart the ESP32 (macOS USB driver; seen often, not always; dtr/rts
    False and stty -hupcl do not help) -> start this program FIRST, then start a trial.
OLD WINDOW (no GUI):    add --nogui   (OpenCV window; keys q quit, w wave test, space = stop)

Threads: camera loop (YOLO + hands + wave) | grabber (newest frame) | sender (CAM 12/s) | serial reader | keyboard
         and the GUI (Tkinter) on the main thread. They share only 'latest' dicts (replaced whole, never edited).
Logs: logs/<date_time>/  camera.csv (every frame)  sent.csv  esp32.txt (all ESP32 lines except D rows)
                         data.csv (D rows)  events.csv (E rows)
      logs/trials.csv    every trial result (S row) of every run, one row per trial -> the report table
Settings changed in the GUI (person / object conf): camera/settings.json (loaded at start, written on Save)
"""
import os
# MUST be before numpy / torch are imported: without it the ByteTrack tracker (numpy maths) leaves ~7 CPU threads
# spinning -> ~700 % CPU for nothing (measured 2026-11-11: 708 % -> 31 %, same 8 fps, same detections).
os.environ.setdefault("OMP_NUM_THREADS", "1")
import argparse
import csv
import json
import queue
import sys
import threading
import time
from collections import Counter, deque

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision, BaseOptions
from ultralytics import YOLO

# =============================== CONFIG (change here) ===============================
CAM_INDEX = -1                # -1 = find the external USB camera by itself (numbers change when devices are plugged)
CAM_MAX_W = 640               # how it is found: this USB2 camera gives at most 640x480; the MacBook / iPhone cameras
                              # give 1280x720 or more -> the first camera that stays <= CAM_MAX_W wide is ours
WIDTH, HEIGHT = 640, 480
FLIP_H, FLIP_V = True, False  # this camera gives a mirrored image -> flip back
USE_MJPG = True               # this USB2 camera: MJPG ~8 fps, without MJPG only ~2 fps
DEVICE = "mps"                # Apple GPU ("cpu" if it fails)
YOLO_IMGSZ = 416
HAND_SCALE = 0.5
PERSON_CONF = 0.3             # low enough that a person at the edge / turned sideways is not lost  (GUI: Camera tab)
OBJECT_CONF = 0.35            # (GUI: Camera tab; the GUI value in settings.json wins)
# COCO class name -> object_id sent to the ESP32 (0 = no object). Classes not listed are ignored.
OBJECT_IDS = {"cup": 1, "bottle": 2, "cell phone": 3, "teddy bear": 4, "sports ball": 5,
              "book": 6, "scissors": 7, "remote": 8, "banana": 9, "apple": 9, "orange": 9}
SEND_HZ = 12                  # CAM lines per second (latest result repeated if the camera is slower)
BAUD = 115200
# --- wave detector: an OPEN hand going left-right-left (anywhere in the image) ---
OPEN_FINGERS = 3              # fingers that must be straight for an "open hand"
HAND_CONF = 0.7               # MediaPipe hand detection / presence confidence (default 0.5) - fewer fake hands
HAND_NEAR_PERSON = 0.6        # the hand must be inside the person box widened by this x box width on each side
HAND_SIZE = (0.06, 0.6)       # wrist->palm length relative to the person box height (a real hand is in this range)
WAVE_MIN_MOVE = 0.06          # a swing must be at least this wide (x units, image width = 2.0)
WAVE_FLIPS = 3                # direction changes needed ...
WAVE_WINDOW_S = 2.5           # ... within this time
WAVE_COOLDOWN_S = 4.0         # no new WAVE for this long (the robot waves back ~3 s)
WAVE_HAND_LOST_S = 0.5        # hand gone this long -> start counting again
WAVE_EMOTIONS = {"normal", "happy"}   # with the ESP32: detect only while the head is still
# --- object confirm + lock ---
LOCK_FRAMES = 6               # a new object is voted over this many frames (~0.7 s) before it is sent at all
TRACK_FORGET_S = 3.0          # a lost track is remembered this long (re-found nearby -> keeps its locked class)
REFIND_DIST = 0.25            # "nearby" = centre moved less than this part of the image width
# --- GUI ---
GUI_W, GUI_H = 480, 360       # camera picture size in the GUI (made in the camera thread)
GUI_FRAME_S = 0.1             # the camera thread prepares a GUI picture at most this often (10/s)
# ====================================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "settings.json")
LOG_ROOT = os.path.join(HERE, "logs")

ap = argparse.ArgumentParser()
ap.add_argument("--port", help="ESP32 serial port; without it = TEST MODE (nothing is sent)")
ap.add_argument("--cam", type=int, default=CAM_INDEX, help="camera number, -1 = find the external USB camera")
ap.add_argument("--nogui", action="store_true", help="old OpenCV window instead of the GUI")
ap.add_argument("--webport", type=int, default=8080, help="the GUI as a web page for an iPad on the same WiFi (0 = off)")
args = ap.parse_args()


# ---------------------------------- settings (GUI Camera tab) ----------------------------------
WEB_PIN = ""                        # PIN of the iPad GUI page (made once, kept in settings.json)

def load_settings():
    global PERSON_CONF, OBJECT_CONF, WEB_PIN
    try:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
        WEB_PIN = str(s.get("web_pin", ""))
        PERSON_CONF = min(max(float(s.get("person_conf", PERSON_CONF)), 0.1), 0.9)
        OBJECT_CONF = min(max(float(s.get("object_conf", OBJECT_CONF)), 0.1), 0.9)
        print(f"settings.json: person conf {PERSON_CONF}, object conf {OBJECT_CONF}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print("settings.json ignored:", e)
    if not WEB_PIN.isdigit():               # first start: make the PIN, keep it (conf values stay as in the code)
        import random
        WEB_PIN = f"{random.randint(0, 9999):04d}"
        write_settings({"web_pin": WEB_PIN})

def cam_settings():
    return {"cam:person_conf": PERSON_CONF, "cam:object_conf": OBJECT_CONF}

def set_cam(key, v):
    global PERSON_CONF, OBJECT_CONF
    v = min(max(float(v), 0.1), 0.9)
    if key == "cam:person_conf":
        PERSON_CONF = v
    elif key == "cam:object_conf":
        OBJECT_CONF = v

def write_settings(new):
    """merge into settings.json (keys not given are kept)"""
    try:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.update(new)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=1)

def save_cam():
    write_settings({"person_conf": PERSON_CONF, "object_conf": OBJECT_CONF})

load_settings()


# ---------------------------------- helpers ----------------------------------
def norm(cx, cy):
    return round(cx / WIDTH * 2 - 1, 2), round(cy / HEIGHT * 2 - 1, 2)


class Grabber(threading.Thread):
    """reads the camera continuously -> the camera loop always gets the newest frame"""
    def __init__(self, cap):
        super().__init__(daemon=True)
        self.cap, self.frame, self.n, self.lock, self.ok = cap, None, 0, threading.Lock(), True
    def run(self):
        bad = 0
        while True:
            ok, f = self.cap.read()
            if ok:
                bad = 0
                f = f.copy()                       # own copy: the driver may reuse its buffer (torn / doubled image)
                with self.lock:
                    self.frame, self.n = f, self.n + 1
            else:
                bad += 1
                self.ok = bad < 30
                time.sleep(0.03)
    def get(self):
        with self.lock:
            return (None if self.frame is None else self.frame.copy()), self.n


class WaveDetector:
    """counts left/right direction changes of an open hand"""
    def __init__(self):
        self.reset(); self.last_wave = -1e9
    def reset(self):
        self.dir, self.ext, self.flips, self.last_seen = 0, None, deque(), -1e9
    def update(self, t, hand_x):
        """hand_x = x of the open hand, or None. Returns True once when a wave is recognised."""
        if hand_x is None:
            if t - self.last_seen > WAVE_HAND_LOST_S:
                self.reset()
            return False
        self.last_seen = t
        if self.ext is None:                               # first point: remember it
            self.ext = hand_x
            return False
        if self.dir == 0:                                  # direction not known yet
            if hand_x - self.ext > WAVE_MIN_MOVE: self.dir, self.ext = 1, hand_x
            elif self.ext - hand_x > WAVE_MIN_MOVE: self.dir, self.ext = -1, hand_x
        elif self.dir > 0:
            if hand_x > self.ext: self.ext = hand_x
            elif self.ext - hand_x > WAVE_MIN_MOVE: self.dir, self.ext = -1, hand_x; self.flips.append(t)
        else:
            if hand_x < self.ext: self.ext = hand_x
            elif hand_x - self.ext > WAVE_MIN_MOVE: self.dir, self.ext = 1, hand_x; self.flips.append(t)
        while self.flips and t - self.flips[0] > WAVE_WINDOW_S:
            self.flips.popleft()
        if len(self.flips) >= WAVE_FLIPS and t - self.last_wave > WAVE_COOLDOWN_S:
            self.last_wave = t
            self.flips.clear()
            return True
        return False


# ---------------------------------- logs ----------------------------------
log_dir = os.path.join(LOG_ROOT, time.strftime("%Y%m%d_%H%M%S"))
os.makedirs(log_dir, exist_ok=False)
log_lock = threading.Lock()                # several threads write / flush the log files
logs_open = True                           # False after finish(): late writes from other threads are dropped
f_cam = open(os.path.join(log_dir, "camera.csv"), "w", newline="")
w_cam = csv.writer(f_cam)
w_cam.writerow(["pc_ms", "seq", "fps", "cam_fps", "person", "person_conf", "object", "object_name", "object_id",
                "object_conf", "x", "y", "hands", "hand_x", "hand_y", "open_hand", "flips", "wave", "yolo_ms", "hand_ms"])
f_sent = open(os.path.join(log_dir, "sent.csv"), "w", newline="")
w_sent = csv.writer(f_sent); w_sent.writerow(["pc_ms", "line"])
f_esp = open(os.path.join(log_dir, "esp32.txt"), "w")
T0 = time.monotonic()
def pc_ms(): return int((time.monotonic() - T0) * 1000)


class RowLog:
    """ESP32 CSV rows (D / E) -> one csv file; the ESP32 prints the header line first (e.g. 'D,t_ms,trial_s,...')"""
    def __init__(self, name):
        self.f, self.w, self.header = open(os.path.join(log_dir, name), "w", newline=""), None, None
        self.w = csv.writer(self.f)
    def add(self, fields, is_header):
        if is_header:
            if fields != self.header:              # same header again after a restart -> not repeated
                self.header = fields
                self.w.writerow(["pc_ms"] + fields)
        elif self.header:
            self.w.writerow([pc_ms()] + fields)

def save_trial(fields):
    """S row (one finished trial) -> logs/trials.csv, appended run after run (the report table)"""
    global s_header
    path = os.path.join(LOG_ROOT, "trials.csv")
    if fields[0] == "cond":                        # the header line the ESP32 prints before each result
        s_header = fields
        return
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date_time", "log_dir"] + (s_header or [f"col{i}" for i in range(len(fields))]))
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), os.path.basename(log_dir)] + fields)

s_header = None
d_log, e_log = RowLog("data.csv"), RowLog("events.csv")


# ---------------------------------- ESP32 link (optional) ----------------------------------
ser, ser_lock = None, threading.Lock()
esp_emotion = "normal"             # last 'emotion -> X' seen from the ESP32 (wave gating)
port_ok = False
lines = queue.Queue(maxsize=2000)  # ESP32 lines for the GUI (not D / E rows)
d_state = (0, None, {})            # (count, monotonic time, {column: text}) of the newest D row - replaced whole
d_cols = None                      # D header columns
tune_vals, tune_saved = {}, None   # newest 'tune ... saved|unsaved' answer of the ESP32 (for the iPad page)
esp_forced = None                  # forced emotion (from the 'emotion <name>' answers), None = automatic
# iPad page history (the iPad draws the graphs itself; it only fetches what is new)
WEB_D_COLS = ["base_f", "head_f", "social_R", "novelty_R", "boredom_R", "stress_R", "fatigue_R", "o1", "o2"]
d_hist = deque(maxlen=600)         # (seq, [values of WEB_D_COLS, None = invalid]) = 30 s at 20 rows/s
web_log, web_log_n = deque(maxlen=300), 0   # GUI log lines (seq, text) for the iPad log box
web_lock = threading.Lock()

def web_note(text):
    global web_log_n
    with web_lock:
        web_log_n += 1
        web_log.append((web_log_n, text))

def send(line):
    """send one line to the ESP32 (or only log it in TEST MODE)"""
    global port_ok
    with log_lock:
        if logs_open:
            w_sent.writerow([pc_ms(), line])
    if ser is None or not port_ok:
        return
    try:
        with ser_lock:
            ser.write((line + "\n").encode("ascii", "replace"))
    except Exception:
        port_ok = False

def open_port():
    import serial
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = args.port, BAUD, 0.1
    s.dtr = False; s.rts = False            # (does not stop the reset on this Mac, but does not hurt)
    s.open()
    return s

def to_gui(line):
    web_note(line)
    if not args.nogui:
        try:
            lines.put_nowait(line)
        except queue.Full:                  # GUI not reading (closing) -> drop, never block the reader
            pass

def handle_line(line):
    """one line from the ESP32"""
    global esp_emotion, d_state, d_cols, tune_vals, tune_saved, esp_forced
    if line.startswith("D,"):
        f = line[2:].split(",")
        if f and f[0] == "t_ms":
            d_cols = f
        elif d_cols and len(f) == len(d_cols):
            row = dict(zip(d_cols, f))
            d_state = (d_state[0] + 1, time.monotonic(), row)
            vals = []
            for k in WEB_D_COLS:
                v = row.get(k, "")
                if k in ("base_f", "head_f") and row.get(k[:4] + "_ok") != "1":
                    v = ""                          # invalid ToF -> gap in the graph (never 0)
                try:
                    vals.append(round(float(v), 3) if v != "" else None)
                except ValueError:
                    vals.append(None)
            d_hist.append((d_state[0], vals))
        with log_lock:
            if logs_open:
                d_log.add(f, f[0] == "t_ms")
        return                              # D rows: data.csv only (20 per second - not in esp32.txt)
    with log_lock:
        if not logs_open:
            return
        f_esp.write(f"{pc_ms()},{line}\n")
        if line.startswith("E,"):
            f = line[2:].split(",")
            e_log.add(f, f[0] == "t_ms")
            return
        if line.startswith("S,"):
            save_trial(line[2:].split(","))
    if line.startswith("emotion -> "):
        esp_emotion = line.split("->", 1)[1].strip()
    w = line.split()
    if line == "emotion back to automatic":
        esp_forced = None
    elif len(w) == 2 and w[0] == "emotion" and w[1] in ("normal", "sleepy", "excited", "happy", "interested",
                                                        "bored", "afraid", "tired"):
        esp_forced = w[1]
    if len(w) >= 2 and w[0] == "tune" and w[-1] in ("saved", "unsaved"):
        v = {}
        for k, x in zip(w[1:-1:2], w[2:-1:2]):
            try:
                v[k] = float(x)
            except ValueError:
                pass
        tune_vals, tune_saved = v, w[-1] == "saved"
    if args.nogui:
        print("ESP32:", line)
    to_gui(line)

def reader():
    """ESP32 -> GUI + logs; reconnects if the cable is unplugged"""
    global ser, port_ok
    buf = b""
    while True:
        if not port_ok:
            try:
                if ser: ser.close()
                ser = open_port(); port_ok = True; buf = b""
                print(f"[port {args.port} OK]"); to_gui(f"[port {args.port} OK]")
            except Exception:
                time.sleep(2); continue
        try:
            data = ser.read(256)
        except Exception:
            print("[port LOST - retrying]"); to_gui("[port LOST - retrying]"); port_ok = False; continue
        buf += data
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("ascii", "replace").strip()
            if line:
                handle_line(line)

def keyboard():
    """type a command + Enter in the terminal -> sent to the ESP32"""
    for line in sys.stdin:
        line = line.strip()
        if line:
            send(line); print(f"[sent] {line}" if ser else f"[TEST MODE - not sent] {line}")

if args.port:
    threading.Thread(target=reader, daemon=True).start()
    time.sleep(0.5)
threading.Thread(target=keyboard, daemon=True).start()


# ---------------------------------- camera + models ----------------------------------
def find_camera():
    """camera number of the external USB camera: try 0..3, ask each for 1280x720, keep the one that stays small"""
    if args.cam >= 0:
        return args.cam
    found = []
    for i in range(4):
        c = cv2.VideoCapture(i)
        if not c.isOpened():
            c.release(); continue
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); c.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        ok, f = False, None
        for _ in range(5):                     # the first frames can be empty while the camera starts
            ok, f = c.read()
            if ok: break
            time.sleep(0.1)
        c.release()
        if ok:
            found.append((i, f.shape[1], f.shape[0]))
    print("cameras:", ", ".join(f"{i}: {w}x{h}" for i, w, h in found) or "none")
    for i, w, h in found:
        if w <= CAM_MAX_W:
            print(f"-> using camera {i} (the external USB camera, max {w}x{h})")
            return i
    i = 1 if any(k == 1 for k, _, _ in found) else 0
    print(f"!! external USB camera NOT found (is it plugged in?) -> using camera {i}. Check the picture!")
    to_gui(f"!! external USB camera NOT found -> camera {i} (check the picture; plug it in and restart)")
    return i

def open_camera(wait_s=20):
    t_end = time.time() + wait_s
    while time.time() < t_end:
        c = cv2.VideoCapture(cam_index)
        if c.isOpened() and c.read()[0]:
            return c
        c.release(); print("waiting for the camera... (click 'Allow' if macOS asks)"); time.sleep(2)
    raise SystemExit("cannot open the camera")

print("loading models ...")
yolo = YOLO(os.path.join(HERE, "yolo11n.pt"))
KEEP = [i for i, n in yolo.names.items() if n == "person" or n in OBJECT_IDS]   # only the classes we use
hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=os.path.join(HERE, "hand_landmarker.task")),
    running_mode=vision.RunningMode.VIDEO, num_hands=2,
    min_hand_detection_confidence=HAND_CONF, min_hand_presence_confidence=HAND_CONF))
cam_index = find_camera()
cap = open_camera()
if USE_MJPG:
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT); cap.set(cv2.CAP_PROP_FPS, 30)
grab = Grabber(cap); grab.start()
yolo.predict(np.zeros((HEIGHT, WIDTH, 3), np.uint8), imgsz=YOLO_IMGSZ, device=DEVICE, verbose=False)

latest = {"line": "CAM,0,0,0,0,0.00,0.00"}
cam_state = {}                      # newest camera result for the GUI - replaced whole every frame
stop = threading.Event()

def sender():
    """CAM at SEND_HZ even if the camera is slower (ESP32 treats > 1 s of silence as 'camera lost')"""
    while not stop.is_set():
        if grab.ok:
            send(latest["line"])
        time.sleep(1.0 / SEND_HZ)
threading.Thread(target=sender, daemon=True).start()

print(f"{'TEST MODE - nothing is sent to the robot' if not args.port else 'sending to ' + args.port}. Logs: {log_dir}")

wave = WaveDetector()
locks, raw_names = {}, {}       # per tracked object: confirm votes / locked class ; raw class counts (report)
focus_tid = None                # the ONE object being looked at (track id)
person_focus = {"tid": None, "cx": 0.5, "seen": -99.0}   # the ONE person being looked at (others are ignored)
wave_test = True                # in TEST MODE the wave detector always runs; 'w' toggles it (--nogui)
n_waves = 0


def camera_loop():
    """YOLO + hands + wave on every new frame -> CAM line, logs, cam_state (GUI) / OpenCV window (--nogui)"""
    global focus_tid, n_waves, wave_test, cam_state, person_focus
    seq, last_n, fps, t_prev = 0, 0, 0.0, time.time()
    cam_frames, cam_t, cam_fps = 0, time.time(), 0.0
    wave_until, gui_t = 0.0, 0.0
    while not stop.is_set():
        frame, n = grab.get()
        if frame is None or n == last_n:
            if args.nogui and (cv2.waitKey(1) & 0xFF) == ord("q"):
                stop.set()
            time.sleep(0.002); continue
        cam_frames += n - last_n; last_n = n
        if time.time() - cam_t >= 1:
            cam_fps, cam_frames, cam_t = cam_frames / (time.time() - cam_t), 0, time.time()
        frame = cv2.resize(frame, (WIDTH, HEIGHT))
        if FLIP_H or FLIP_V:
            frame = cv2.flip(frame, -1 if (FLIP_H and FLIP_V) else (1 if FLIP_H else 0))
        t = time.monotonic()
        p_conf_min, o_conf_min = PERSON_CONF, OBJECT_CONF       # GUI may change them: read once per frame

        # ---- YOLO: person + objects ----
        t_a = time.perf_counter()
        res = yolo.track(frame, persist=True, tracker="bytetrack.yaml", imgsz=YOLO_IMGSZ,
                         conf=min(p_conf_min, o_conf_min), classes=KEEP, device=DEVICE, verbose=False)[0]
        t_b = time.perf_counter()
        person_box, obj_box, obj_name, p_conf, o_conf = None, None, "", None, None
        boxes = []
        for b in res.boxes:
            name, conf = res.names[int(b.cls)], float(b.conf)
            if name == "person":
                boxes.append((name, conf, b.xyxy[0], int(b.id) if b.id is not None else None)); continue
            if b.id is None or name not in OBJECT_IDS:
                continue                                   # untracked object box: not confirmed -> ignored
            tid = int(b.id)
            x1, y1, x2, y2 = map(float, b.xyxy[0]); cx = (x1 + x2) / 2 / WIDTH
            L = locks.get(tid)
            if L is None:                                  # new track: re-found an object that was just lost nearby?
                L = {"votes": Counter(), "n": 0, "name": None, "seen": t, "cx": cx}
                for old in locks.values():
                    if old["name"] and 0.2 < t - old["seen"] < TRACK_FORGET_S and abs(old["cx"] - cx) < REFIND_DIST:
                        L["name"] = old["name"]; break     # same thing again -> same locked class
                locks[tid] = L
            L["seen"], L["cx"] = t, cx
            raw_names.setdefault(tid, Counter())[name] += 1
            if L["name"] is None:                          # still confirming: vote
                L["votes"][name] += conf; L["n"] += 1
                if L["n"] >= LOCK_FRAMES:
                    L["name"] = max(L["votes"], key=L["votes"].get)
                    print(f"object track {tid} LOCKED as '{L['name']}' (id {OBJECT_IDS[L['name']]}) "
                          f"votes {dict((k, round(v, 1)) for k, v in L['votes'].items())}")
                else:
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (150, 150, 150), 1)
                    cv2.putText(frame, f"confirming {L['n']}/{LOCK_FRAMES}", (int(x1), int(y1) - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                    continue
            boxes.append((L["name"], conf, b.xyxy[0], tid))
        for tid in [k for k, L in locks.items() if t - L["seen"] > TRACK_FORGET_S]:
            locks.pop(tid)
        # ONE object at a time: keep the one already in focus while it is visible, otherwise take the CLEAREST
        # (highest confidence) confirmed object. Every other object is ignored.
        objs = [bx for bx in boxes if bx[0] != "person" and bx[1] >= o_conf_min]
        chosen = next((bx for bx in objs if bx[3] == focus_tid), None)
        if chosen is None and objs:
            chosen = max(objs, key=lambda bx: bx[1])
            if chosen[3] != focus_tid:
                print(f"focus on object track {chosen[3]} '{chosen[0]}' (conf {chosen[1]:.2f})")
            focus_tid = chosen[3]
        # ONE person at a time too: keep the person already in focus (same track id) while visible. Lost for a
        # moment (track id changed) -> take the person nearest to where the focused one was (within REFIND_DIST,
        # for TRACK_FORGET_S). Nobody in focus -> the BIGGEST (nearest) person. Everyone else is ignored
        # (also for the wave: only the focused person's hand counts).
        def pcx(bx): return float(bx[2][0] + bx[2][2]) / 2 / WIDTH
        def parea(bx): return float((bx[2][2] - bx[2][0]) * (bx[2][3] - bx[2][1]))
        people = [bx for bx in boxes if bx[0] == "person" and bx[1] >= p_conf_min]
        pf = person_focus
        pchosen = next((bx for bx in people if pf["tid"] is not None and bx[3] == pf["tid"]), None)
        if pchosen is None and people:
            near = [bx for bx in people if abs(pcx(bx) - pf["cx"]) < REFIND_DIST]
            if near and t - pf["seen"] < TRACK_FORGET_S:
                pchosen = min(near, key=lambda bx: abs(pcx(bx) - pf["cx"]))
            else:
                pchosen = max(people, key=parea)
            if pchosen[3] != pf["tid"]:
                print(f"focus on person track {pchosen[3]}")
        if pchosen is not None:
            pf["tid"], pf["cx"], pf["seen"] = pchosen[3], pcx(pchosen), t
        for name, conf, xyxy, tid in boxes:
            x1, y1, x2, y2 = map(int, xyxy); area = (x2 - x1) * (y2 - y1)
            if name == "person":
                if conf < p_conf_min:
                    continue
                if pchosen is not None and xyxy is pchosen[2]:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 3)
                    cv2.putText(frame, "person (FOCUS)", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)
                    person_box, p_conf = (x1, y1, x2, y2, area), conf
                else:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (110, 110, 110), 1)   # other people: ignored
                    cv2.putText(frame, "ignored", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (110, 110, 110), 1)
            elif chosen is not None and tid == chosen[3]:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 160, 0), 3)
                cv2.putText(frame, f"{name} id{OBJECT_IDS[name]} {conf:.2f} (LOCKED)", (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 160, 0), 1)
                obj_box, obj_name, o_conf = (x1, y1, x2, y2, area), name, conf
            else:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (110, 110, 110), 1)       # other objects: ignored
                cv2.putText(frame, "ignored", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (110, 110, 110), 1)

        # ---- MediaPipe: hands; the wave hand = the biggest OPEN hand ----
        small = cv2.resize(frame, None, fx=HAND_SCALE, fy=HAND_SCALE)
        hr = hands.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                             data=np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))),
                                    pc_ms())
        t_c = time.perf_counter()
        hand_px, hand_size = None, 0
        for lm in hr.hand_landmarks:
            pts = np.array([(p.x * WIDTH, p.y * HEIGHT) for p in lm], float)
            wrist = pts[0]
            # a finger is straight when its tip is further from the wrist than its middle joint
            straight = sum(np.linalg.norm(pts[tip] - wrist) > np.linalg.norm(pts[pip] - wrist) * 1.15
                           for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)))
            is_open = straight >= OPEN_FINGERS
            # a waving hand belongs to a PERSON: near the person box and of a believable size (a curtain is not)
            size = np.linalg.norm(pts[9] - wrist)
            why = ""
            if person_box is None:
                why = "no person"
            else:
                px1, py1, px2, py2 = person_box[:4]; pw, ph = px2 - px1, py2 - py1
                if not (px1 - HAND_NEAR_PERSON * pw <= pts[9][0] <= px2 + HAND_NEAR_PERSON * pw
                        and py1 - 0.3 * ph <= pts[9][1] <= py2):
                    why = "far from person"
                elif not (HAND_SIZE[0] * ph <= size <= HAND_SIZE[1] * ph):
                    why = "wrong size"
            if why:
                is_open = False
            col = (0, 220, 255) if is_open else (120, 120, 120)
            for (px, py) in pts.astype(int):
                cv2.circle(frame, (px, py), 2, col, -1)
            palm = pts[9].astype(int)                          # middle-finger base = palm centre
            cv2.putText(frame, why or ("open" if is_open else "closed"), (palm[0] + 12, palm[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
            if is_open and size > hand_size:
                hand_px, hand_size = palm, size                # the biggest (closest) open hand
        hand_x = hand_y = None
        if hand_px is not None:
            hand_x, hand_y = norm(*hand_px)
            cv2.circle(frame, tuple(int(v) for v in hand_px), 10, (0, 220, 255), 2)

        # ---- wave ----
        allowed = wave_test if not args.port else (esp_emotion in WAVE_EMOTIONS)
        waved = wave.update(t, hand_x) if allowed else (wave.reset() or False)

        # ---- CAM line ----
        person, obj = (1 if person_box else 0), (1 if obj_box else 0)
        oid = OBJECT_IDS[obj_name] if obj else 0
        if obj_box:
            x, y = norm((obj_box[0] + obj_box[2]) / 2, (obj_box[1] + obj_box[3]) / 2)
        elif person_box:
            x, y = norm((person_box[0] + person_box[2]) / 2, person_box[1] + 0.25 * (person_box[3] - person_box[1]))
        else:
            x, y = 0.0, 0.0
        latest["line"] = f"CAM,{seq},{person},{obj},{oid},{x:.2f},{y:.2f}"
        if waved:
            send(f"WAVE,{seq},{hand_x:.2f}")
            n_waves += 1; wave_until = time.time() + 3.0
            print(f"WAVE,{seq},{hand_x:.2f}   (waves so far: {n_waves})")
            to_gui(f"[camera] WAVE (x {hand_x:.2f}) - waves so far {n_waves}")
        if obj or person:
            cv2.drawMarker(frame, (int((x + 1) / 2 * WIDTH), int((y + 1) / 2 * HEIGHT)), (0, 0, 255),
                           cv2.MARKER_CROSS, 20, 2)

        now = time.time()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3); t_prev = now
        with log_lock:
            if logs_open:
                w_cam.writerow([pc_ms(), seq, f"{fps:.1f}", f"{cam_fps:.1f}", person, f"{p_conf:.2f}" if p_conf else "",
                                obj, obj_name, oid, f"{o_conf:.2f}" if o_conf else "", x, y, len(hr.hand_landmarks),
                                "" if hand_x is None else hand_x, "" if hand_y is None else hand_y,
                                int(hand_x is not None), len(wave.flips), int(waved),
                                f"{1000*(t_b-t_a):.0f}", f"{1000*(t_c-t_b):.0f}"])
        seq = (seq + 1) % 65536
        if seq % 20 == 0:                       # status in the terminal + make sure the logs reach the disk
            print(f"fps {fps:4.1f} | camera {cam_fps:4.1f} | yolo {1000*(t_b-t_a):3.0f} ms | "
                  f"hands {1000*(t_c-t_b):3.0f} ms | {latest['line']}")
            with log_lock:
                if logs_open:
                    for f in (f_cam, f_sent, f_esp, d_log.f, e_log.f):
                        f.flush()

        # ---- picture: GUI (10/s, small, RGB, made here so the GUI thread does no work) or OpenCV window ----
        if not args.nogui:
            if now - gui_t >= GUI_FRAME_S:
                gui_t = now
                rgb = cv2.cvtColor(cv2.resize(frame, (GUI_W, GUI_H), interpolation=cv2.INTER_AREA),
                                   cv2.COLOR_BGR2RGB)
            else:
                rgb = cam_state.get("rgb")
            cam_state = {"rgb": rgb, "person": person, "obj_name": obj_name if obj else "", "obj_id": oid,
                         "waves": n_waves, "wave_until": wave_until, "fps": fps, "wave_on": allowed}
            continue
        mode = "TEST MODE" if not args.port else (f"ESP32 {'OK' if port_ok else 'LOST'} | emotion {esp_emotion}")
        cv2.putText(frame, f"fps {fps:4.1f} (camera {cam_fps:4.1f}) | {mode}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, f"wave {'ON' if allowed else 'off'}  flips {len(wave.flips)}/{WAVE_FLIPS}  waves {n_waves}",
                    (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2)
        if time.time() < wave_until - 2.0:
            cv2.putText(frame, "WAVE!", (WIDTH // 2 - 80, HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 4)
        cv2.putText(frame, latest["line"], (10, HEIGHT - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imshow("lamp camera (q quit, w wave test, space stop)", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            stop.set()
        if k == ord("w"):
            wave_test = not wave_test
        if k == ord(" "):
            send("stop"); print("[STOP sent]" if ser else "[TEST MODE - stop not sent]")


class Api:
    """what the GUI may use (gui.py never touches the port, the camera or the files directly)"""
    web_url = ""                       # iPad GUI link (shown at the bottom of the GUI)
    lines = lines
    connected = bool(args.port)
    @staticmethod
    def send(c):
        web_note(f"→ {c}")
        send(c)
    cam_settings = staticmethod(cam_settings)
    set_cam = staticmethod(set_cam)
    save_cam = staticmethod(save_cam)
    @staticmethod
    def latest_d(): return d_state
    @staticmethod
    def cam(): return cam_state
    @staticmethod
    def on_close(): stop.set()
    @staticmethod
    def stopping(): return stop.is_set()


class WebApi:
    """what the iPad page (web.py) may use - everything the desktop GUI shows"""
    @staticmethod
    def state(since_d=0, since_log=0):
        n, t, d = d_state
        vals = dict(tune_vals)
        try:
            vals["phi"] = float(d["phi"])
        except (KeyError, ValueError):
            pass
        temps = {}
        for j in ("base", "shoulder", "elbow", "pitch", "yaw"):
            try:
                vals["j:" + j] = float(d[j + "_cmd"])
            except (KeyError, ValueError):
                pass
            try:
                temps[j] = float(d[j + "_temp"])
            except (KeyError, ValueError):
                temps[j] = None
        vals.update(cam_settings())
        link = bool(args.port) and t is not None and time.monotonic() - t < 1.0
        if since_d > n:                            # this program restarted, the page did not: start again
            since_d = 0
        rows = [r for r in list(d_hist) if r[0] > since_d]
        with web_lock:
            logs = [x for x in web_log if x[0] > since_log]
        cam = cam_state

        def f(k):
            try:
                return float(d[k])
            except (KeyError, ValueError):
                return None
        return {"connected": bool(args.port), "link": link, "emotion": d.get("emotion", ""), "forced": esp_forced,
                "auto": None if d.get("auto") not in ("0", "1") else d["auto"] == "1",
                "cond": None if d.get("cond") not in ("0", "1") else int(d["cond"]),
                "trial_s": f("trial_s"), "napping": d.get("napping") == "1",
                "tof": {"base": [f("base_f") if d.get("base_ok") == "1" else None, f("base_raw")],
                        "head": [f("head_f") if d.get("head_ok") == "1" else None, f("head_raw")]},
                "saved": tune_saved, "values": vals, "temps": temps,
                "seq": n, "rows": rows, "log_seq": web_log_n, "log": logs,
                "cam": {"ok": "rgb" in cam, "person": bool(cam.get("person")), "obj": cam.get("obj_name", ""),
                        "obj_id": cam.get("obj_id", 0), "waves": cam.get("waves", 0),
                        "waving": time.time() < cam.get("wave_until", 0), "fps": round(cam.get("fps", 0), 1)}}
    _jpg = (None, b"")
    @staticmethod
    def jpeg():
        """newest camera picture as JPEG - encoded only when asked, and once per new picture"""
        rgb = cam_state.get("rgb")
        if rgb is None:
            return b""
        if WebApi._jpg[0] is not rgb:
            ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 70])
            WebApi._jpg = (rgb, buf.tobytes() if ok else b"")
        return WebApi._jpg[1]
    @staticmethod
    def run(c):
        to_gui(f"[iPad] → {c}")
        if c.startswith("cam:"):
            key, v = c.split()
            set_cam(key, v)
        elif c == "camsave":
            save_cam()
        else:
            send(c)

def finish():
    global logs_open
    print("\nobject stability (raw class per frame BEFORE the lock - choose demo objects that are mostly ONE class):")
    for tid, c in raw_names.items():
        n = sum(c.values())
        if n >= 10:
            print(f"  track {tid}: " + ", ".join(f"{k} {100*v/n:.0f}%" for k, v in c.most_common()) + f"  ({n} frames)")
    with log_lock:
        logs_open = False
        for f in (f_cam, f_sent, f_esp, d_log.f, e_log.f):
            f.close()
    cap.release()
    if args.nogui:
        cv2.destroyAllWindows()
    print("logs saved in", log_dir)


try:
    if args.nogui:
        camera_loop()                          # OpenCV window must stay on the main thread
    else:
        import gui
        if args.webport:
            try:
                import web
                Api.web_url = web.start(WebApi, args.webport, WEB_PIN)
                print("iPad GUI (same WiFi):", Api.web_url)
            except OSError as e:
                print(f"iPad page OFF - port {args.webport} busy? ({e})")
        def camera_thread():
            try:
                camera_loop()
            except Exception:                  # never die silently: show it in the GUI log and the terminal
                if stop.is_set():              # closing: torch may already be shutting down - not an error
                    return
                import traceback
                traceback.print_exc()
                to_gui("[camera] CRASHED - see the terminal: " + traceback.format_exc().strip().splitlines()[-1])
                cam_state.clear()
        cam_thread = threading.Thread(target=camera_thread, daemon=True)
        cam_thread.start()
        import signal
        signal.signal(signal.SIGINT, lambda *a: stop.set())   # Ctrl+C: the GUI sees 'stop' and closes itself
        gui.run(Api)                           # Tkinter on the main thread (macOS); returns when the window closes
        stop.set()
        cam_thread.join(timeout=3)             # let the camera thread finish its frame before files close
except KeyboardInterrupt:                      # Ctrl+C = quit (--nogui)
    stop.set()
finish()
