"""gui.py - the robot's GUI (Tkinter, dark). Started by lamp_camera.py (do not run it alone).

Pages:  Monitor = camera + ToF graphs      Control = hormones, CPG, and the Motors card (Joints | CPG | ToF | Camera)
Data :  D rows from the ESP32 ('log on 1', 20 per second), 'tune ...' answers, the camera thread's latest result.
Values: - / + / typing only change the NEW box. Nothing is sent until ENTER (button or Return).
        Save = keep on the ESP32 (tune save) + camera settings file on the laptop.
Light on resources: graphs 20/s (only when a new D row came, only the visible page), text 5/s and only changed
labels, the camera picture 10/s pasted into ONE image, value rows change only when the ESP32 answers.
"""
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from tkinter import messagebox

from PIL import Image, ImageTk

# ---------------- theme ----------------
BG, CARD, CARD2, LINE = "#121419", "#1b1e25", "#262a33", "#2e333d"
FG, MUTED, ACCENT = "#e8eaed", "#8b919c", "#4c8dff"
OK, WARN, DANGER = "#34c759", "#f5b942", "#ff453a"
FAMILY = "Helvetica Neue"
EMO_RGB = {"normal": (0, 255, 0), "sleepy": (100, 0, 255), "excited": (255, 0, 255), "happy": (255, 130, 0),
           "interested": (255, 255, 255), "bored": (0, 0, 255), "afraid": (255, 0, 0), "tired": (255, 60, 0)}
# (same colours as EMO_RGB in src/brain.cpp - change both. 2026-11-12 user: normal green, happy yellow,
#  interested white, bored blue)
HORMONES = [("social", "มีคนอยู่", "#4c8dff"), ("novelty", "เจอของใหม่", "#ff9f0a"),
            ("boredom", "เบื่อ", "#a0a6b0"), ("stress", "ใกล้เกินไป", "#ff453a"),
            ("fatigue", "มอเตอร์ร้อน", "#bf5af2")]
JOINTS = [("Base", "หมุนฐานซ้าย-ขวา", "base", -90.0, 90.0), ("Shoulder", "ไหล่ ขึ้น-ลง", "shoulder", -58.3, 74.1),
          ("Elbow", "ศอก ขึ้น-ลง", "elbow", -46.7, 2.3), ("Head pitch", "หัวก้ม-เงย", "pitch", -70.8, 33.1),
          ("Head yaw", "หัวหันซ้าย-ขวา", "yaw", -70.8, 64.4)]
# CPG tab: key, title, thai, step, lo, hi, fmt, unit   (phi is not saved: hormones set it while Auto is ON)
CPG_PARAMS = [("phi", "phi", "ความเร็วจังหวะ (ปิด Auto)", 0.01, 0.05, 0.80, "{:.2f}", ""),
              ("alpha", "alpha", "รูปคลื่น / ความแรง", 0.01, 1.01, 1.50, "{:.2f}", ""),
              ("amp", "amp ×", "ขนาดการขยับทั้งหมด", 0.1, 0.0, 2.0, "{:.1f}", "×"),
              ("speed", "speed", "ความเร็วสูงสุดทุกข้อต่อ", 1, 5, 45, "{:.0f}", "°/s")]
TOF_GROUPS = [("object", "Object  ·  base ToF", "มีของตรงหน้าฐาน"),
              ("afraid", "Afraid  ·  head ToF", "กลัว เมื่อของเข้าใกล้หัว"),
              ("jolt", "Jolt  ·  head ToF", "สะดุ้ง เมื่อใกล้มาก"),
              ("person", "Person  ·  base ToF", "คนเดินเข้ามา (ใช้ตอนไม่มีกล้อง)")]
TOF_FIELDS = [("enter", "enter", "ระยะเริ่มนับว่าเจอ", 1, 3, 120, "{:.0f}", "cm"),
              ("exit", "exit", "ระยะที่นับว่าหายไป", 1, 3, 120, "{:.0f}", "cm"),
              ("tin", "t_enter", "ต้องเจอค้างนานเท่านี้", 0.1, 0, 10, "{:.1f}", "s"),
              ("tout", "t_exit", "ต้องหายนานเท่านี้", 0.1, 0, 10, "{:.1f}", "s")]
# Camera tab. "cam:" = setting of the camera program on the laptop (saved in settings.json there, not on the ESP32)
CAM_PARAMS = [("Camera program  ·  laptop", "ตัวจับภาพบนคอม", [
                  ("cam:person_conf", "person conf", "ความมั่นใจขั้นต่ำว่าเป็นคน", 0.05, 0.1, 0.9, "{:.2f}", ""),
                  ("cam:object_conf", "object conf", "ความมั่นใจขั้นต่ำว่าเป็นของ", 0.05, 0.1, 0.9, "{:.2f}", "")]),
              ("Head tracking  ·  ESP32", "หัวหันตามของ", [
                  ("track.speed", "track speed", "ความเร็วที่หัวหันตามของ", 1, 0, 45, "{:.0f}", "°/s"),
                  ("track.start", "track start", "ของห่างกลางภาพเกินเท่านี้ถึงเริ่มหัน 0 = ไม่หัน", 1, 0, 50, "{:.0f}", "%"),
                  ("track.stop", "track stop", "หันจนของห่างกลางภาพไม่เกินเท่านี้ แล้วหยุดนิ่ง", 1, 0, 50, "{:.0f}", "%")])]
# Behaviour tab (ESP32, tune keys)
BEHAV_PARAMS = [("Behaviour  ·  ESP32", "พฤติกรรม", [
                  ("cam.person_out", "person hold", "คนหายจากภาพนานเท่านี้ถึงนับว่าออกไปแล้ว", 1, 0, 30, "{:.0f}", "s"),
                  ("afraid.calm", "afraid calm", "หลังกลัว อยู่ normal นานเท่านี้ก่อนกลับไป happy", 0.5, 0, 10, "{:.1f}", "s"),
                  ("sleep.after", "sleep after", "ไม่เจอใคร/อะไรเลยนานเท่านี้ -> ง่วง หลับ (มอเตอร์ปิด)", 10, 10, 600, "{:.0f}", "s"),
                  ("head.up", "head up", "เงยหัวเพิ่ม (normal/happy/excited) ให้กล้องเห็นคนยืน  + = เงย", 1, -20, 30, "{:.0f}", "°")])]
GRAPH_MS = 50          # graphs: up to 20 per second (a point is added only when a NEW D row came)
TEXT_MS = 200          # numbers / text: 5 per second, changed only when the value really changes
CAM_MS = 100           # camera picture: 10 per second
GRAPH_S = 30           # graph history (seconds)
CAM_W, CAM_H = 480, 360
LINK_TIMEOUT_S = 1.0   # no D row for this long -> ESP32 dot red
HELLO_S = 3.0          # ... and every this long 'log on 1' + 'tune' are sent again until D rows come


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def rgb_of(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def blend(a, b, k):    # k of colour a over colour b (Tk has no transparency)
    a, b = (rgb_of(a) if isinstance(a, str) else a), rgb_of(b)
    return hexc([b[i] + (a[i] - b[i]) * k for i in range(3)])


def text_on(rgb):
    return "#000000" if sum(rgb) > 380 else "#ffffff"


def rrect(c, x1, y1, x2, y2, r, **kw):
    p = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
         x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(p, smooth=True, **kw)


def put(lbl, text, fg=None):
    """change a label ONLY when it really changes (no needless re-layout)"""
    if lbl.cget("text") != text:
        lbl.configure(text=text)
    if fg and lbl.cget("fg") != fg:
        lbl.configure(fg=fg)


def num(d, key):
    """number from a D row; blank / missing -> None (never 0)"""
    try:
        v = d.get(key, "")
        return float(v) if v != "" else None
    except ValueError:
        return None


class Pill(tk.Canvas):
    """rounded flat button. fill/fg can be changed later with style()."""
    def __init__(self, parent, text, cmd, bg, fill=CARD2, fg=FG, size=12, bold=False, padx=14, pady=7, minw=0):
        f = tkfont.Font(family=FAMILY, size=size, weight="bold" if bold else "normal")
        w, h = max(minw, f.measure(text) + 2 * padx), f.metrics("linespace") + 2 * pady
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0, cursor="hand2")
        self.shape = rrect(self, 1, 1, w - 1, h - 1, min(12, h // 2), fill=fill, outline="")
        self.label = self.create_text(w / 2, h / 2, text=text, fill=fg, font=f)
        self.fill = fill
        self.bind("<Button-1>", lambda e: cmd())
        self.bind("<Enter>", lambda e: self.itemconfigure(self.shape, fill=blend("#ffffff", self.fill, 0.12)))
        self.bind("<Leave>", lambda e: self.itemconfigure(self.shape, fill=self.fill))

    def style(self, fill=None, fg=None):
        if fill:
            self.fill = fill
            self.itemconfigure(self.shape, fill=fill)
        if fg:
            self.itemconfigure(self.label, fill=fg)


class Segmented(tk.Frame):
    """row of pills where exactly one is selected (C0/C1, page, tab, auto ON/OFF)."""
    def __init__(self, parent, bg, items, on_pick, size=12):
        super().__init__(parent, bg=bg)
        self.p = {}
        for key, txt in items:
            b = Pill(self, txt, lambda k=key: on_pick(k), bg=bg, size=size, padx=12)
            b.pack(side="left", padx=1)
            self.p[key] = b

    def select(self, key):
        for k, b in self.p.items():
            b.style(fill=ACCENT if k == key else CARD2, fg="#ffffff" if k == key else MUTED)


class Param:
    """one value row:  Title (ไทย)   now 30 cm   [-] [new] [+]
    - / + / typing only change the NEW box; app.apply() (ENTER) sends every changed row at once.
    'now' only changes when the ESP32 (or the camera program) answers -> set_now()."""
    def __init__(self, app, parent, title, thai, step, lo, hi, fmt, unit, to_cmds, bg=CARD2, title_w=10, now_w=7,
                 compact=False):
        self.app, self.step_, self.lo, self.hi, self.fmt, self.unit, self.to_cmds = \
            app, step, lo, hi, fmt, unit, to_cmds
        self.now, self.pending = None, False
        self.row = tk.Frame(parent, bg=bg)
        info = tk.Frame(self.row, bg=bg); info.pack(side="left")
        tk.Label(info, text=title, bg=bg, fg=FG, font=(FAMILY, 12, "bold"), width=title_w, anchor="w").pack(anchor="w")
        if thai:
            tk.Label(info, text=f"({thai})", bg=bg, fg=MUTED, font=(FAMILY, 10), anchor="w").pack(anchor="w")
        self.slot = tk.Frame(self.row, bg=bg); self.slot.pack(side="right")           # extra widgets (temp)
        py = 0 if compact else 1
        Pill(self.row, "+", lambda: self.step(+1), bg=bg, fill=LINE, size=13, padx=10, pady=py).pack(side="right")
        self.e = tk.Entry(self.row, width=6, font=(FAMILY, 12), justify="center", bg=BG, fg=FG,
                          insertbackground=FG, relief="flat", highlightthickness=1, highlightbackground=LINE,
                          highlightcolor=ACCENT)
        self.e.pack(side="right", padx=4, ipady=1 if compact else 3)
        self.e.bind("<Return>", lambda ev: app.apply())
        self.e.bind("<KeyRelease>", lambda ev: ev.keysym != "Return" and self.touch())
        Pill(self.row, "−", lambda: self.step(-1), bg=bg, fill=LINE, size=13, padx=10, pady=py).pack(side="right")
        self.now_lbl = tk.Label(self.row, text="-", bg=bg, fg=FG, font=(FAMILY, 13, "bold"), width=now_w, anchor="e")
        self.now_lbl.pack(side="right", padx=(0, 8))
        if not compact:
            tk.Label(self.row, text="now", bg=bg, fg=MUTED, font=(FAMILY, 10)).pack(side="right")

    def text(self, v):
        return self.fmt.format(v)

    def value(self):
        try:
            return min(max(float(self.e.get()), self.lo), self.hi)
        except ValueError:
            return None

    def step(self, d):
        base = self.value()
        base = self.now if base is None else base
        if base is None:
            return
        v = min(max(round((base + d * self.step_) / self.step_) * self.step_, self.lo), self.hi)
        self.e.delete(0, "end"); self.e.insert(0, self.text(v))
        self.touch()

    def touch(self):
        self.pending = self.e.get().strip() != ("" if self.now is None else self.text(self.now))
        self.app.count_pending()

    def set_now(self, v):
        if v == self.now:
            return
        self.now = v
        put(self.now_lbl, "-" if v is None else self.text(v) + (" " + self.unit if self.unit else ""))
        # the NEW box follows 'now' until the user edits it (never while the cursor is in it)
        if not self.pending and v is not None and self.e.focus_get() is not self.e:
            if self.e.get() != self.text(v):
                self.e.delete(0, "end"); self.e.insert(0, self.text(v))

    def take(self):
        """commands for ENTER (empty if nothing changed); clears the pending mark"""
        v = self.value() if self.pending else None
        self.pending = False
        if v is None:
            if self.now is not None:
                self.e.delete(0, "end"); self.e.insert(0, self.text(self.now))   # bad text -> current value
            return []
        return self.to_cmds(v)


class Graph:
    """lines are created ONCE, each update only moves them. None = no value -> a gap (never drawn as 0)."""
    def __init__(self, parent, w, h, ymin, ymax, colors, n=GRAPH_S * 20, marks=(), fill=False, grid=True, bg=CARD,
                 axis=True):
        self.c = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0)
        self.w, self.h, self.ymin, self.ymax, self.n = w, h, ymin, ymax, n
        self.data = [deque([None] * n, maxlen=n) for _ in colors]
        if grid:
            for k in range(1, 4):
                y = h * k / 4
                self.c.create_line(0, y, w, y, fill=LINE)
        for v, label in marks:
            y = self.y(v)
            self.c.create_line(0, y, w, y, fill=MUTED, dash=(3, 4))
            self.c.create_text(w - 6, y - 8, text=label, anchor="e", fill=MUTED, font=(FAMILY, 9))
        if axis:
            self.c.create_text(4, 9, text=f"{ymax:g}", anchor="w", fill=MUTED, font=(FAMILY, 9))
            self.c.create_text(4, h - 9, text=f"{ymin:g}", anchor="w", fill=MUTED, font=(FAMILY, 9))
        self.fills = [self.c.create_polygon(0, 0, 0, 0, 0, 0, fill=blend(col, bg, 0.22), outline="")
                      if fill else None for col in colors]
        self.segs = [[self.c.create_line(0, 0, 0, 0, fill=col, width=2, capstyle="round", joinstyle="round")
                      for _ in range(4)] for col in colors]           # up to 4 pieces between gaps
        self.dirty = False

    def y(self, v):
        v = min(max(v, self.ymin), self.ymax)
        return self.h - 3 - (v - self.ymin) / (self.ymax - self.ymin) * (self.h - 6)

    def push(self, *values):
        for d, v in zip(self.data, values):
            d.append(v)
        self.dirty = True

    def draw(self):
        if not self.dirty:
            return
        self.dirty = False
        dx = (self.w - 1) / (self.n - 1)
        for d, segs, fid in zip(self.data, self.segs, self.fills):
            pieces, cur = [], []
            for i, v in enumerate(d):
                if v is None:
                    if cur:
                        pieces.append(cur); cur = []
                else:
                    cur += [i * dx, self.y(v)]
            if cur:
                pieces.append(cur)
            pieces = [p for p in pieces if len(p) >= 4][-len(segs):]
            for k, s in enumerate(segs):
                self.c.coords(s, *(pieces[k] if k < len(pieces) else (0, 0, 0, 0)))
            if fid is not None:
                if len(pieces) == 1:
                    p = pieces[0]
                    self.c.coords(fid, *p, p[-2], self.h, p[0], self.h)
                else:
                    self.c.coords(fid, 0, 0, 0, 0, 0, 0)


class App:
    """api (from lamp_camera.py): send(line), lines (queue of ESP32 lines, not D), latest_d() -> (count, t, dict),
    cam() -> dict of the camera thread's newest result, cam_settings() / set_cam(key, v) / save_cam(),
    connected -> bool (a port was given), on_close()"""
    def __init__(self, root, api):
        self.root, self.api = root, api
        self.page, self.forced, self.auto, self.d_seen = 1, None, True, -1
        self.d = {}
        root.title("Lamp Robot")
        root.geometry("1190x830")
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.f = (FAMILY, 12)
        self.f_big = (FAMILY, 24, "bold")
        self.params = []                        # every Param (for ENTER)
        self.tune_p = {}                        # tune key / cam key -> Param
        self.build_top()
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=16, pady=8)
        self.p1, self.p2 = self.build_page1(), self.build_page2()
        self.build_bottom()
        self.show_page(1)
        for k, v in api.cam_settings().items():
            self.tune_p[k].set_now(v)
        self.hello()
        self.graph_tick()
        self.text_tick()
        self.cam_tick()
        self.line_tick()

    def hello(self):
        """ask the ESP32 for data rows + the tuning values (at start, after a restart, and while no D rows come)"""
        self._hello_t = time.monotonic()
        self.send("log on 1", "tune")

    def close(self):
        self.api.on_close()
        self.root.destroy()

    # ---------------- helpers ----------------
    def send(self, *cmds):
        for c in cmds:
            if c:
                self.log(f"→ {c}" + ("" if self.api.connected else "    (TEST MODE: not sent)"))
                self.api.send(c)

    def log(self, s):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", s + "\n")
        if int(self.logbox.index("end-1c").split(".")[0]) > 200:
            self.logbox.delete("1.0", "2.0")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def on_line(self, line):
        """every line from the ESP32 that is not a D / E row"""
        if line.startswith("S,"):
            self.log(line + ("    -> saved in logs/trials.csv" if not line.startswith("S,cond") else ""))
            return
        self.log(line)
        w = line.split()
        if "started" in line or "reset reason" in line:     # the ESP32 restarted -> ask again
            self.root.after(1500, self.hello)
        if len(w) >= 2 and w[0] == "tune" and w[-1] in ("saved", "unsaved"):
            for k, v in zip(w[1:-1:2], w[2:-1:2]):
                if k in self.tune_p:
                    try:
                        self.tune_p[k].set_now(float(v))
                    except ValueError:
                        pass
            put(self.saved_lbl, "● saved on ESP32" if w[-1] == "saved" else "● not saved yet",
                OK if w[-1] == "saved" else MUTED)
        elif line == "emotion back to automatic":
            self.forced = None; self.mark_forced()
        elif len(w) == 2 and w[0] == "emotion" and w[1] in EMO_RGB:
            self.forced = w[1]; self.mark_forced()
        elif line == "auto on":
            self.set_auto(True, send=False)
        elif line == "auto off" or line.startswith("(auto off"):   # 'auto off' / 't' and phi turn it off
            self.set_auto(False, send=False)

    def card(self, parent, title=None, right=None):
        f = tk.Frame(parent, bg=CARD, padx=14, pady=12)
        if title:
            head = tk.Frame(f, bg=CARD); head.pack(fill="x", pady=(0, 8))
            tk.Label(head, text=title.upper(), bg=CARD, fg=MUTED, font=(FAMILY, 10, "bold")).pack(side="left")
            if right:
                right(head)
        return f

    def label(self, parent, text="", fg=FG, font=None, bg=CARD, **kw):
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=font or self.f, **kw)

    # ---------------- top bar ----------------
    def build_top(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 0))

        r1 = tk.Frame(top, bg=BG); r1.pack(fill="x")
        self.badge = tk.Canvas(r1, width=290, height=48, bg=BG, highlightthickness=0)
        self.badge_bg = rrect(self.badge, 1, 1, 289, 47, 22, fill=CARD, outline="")
        self.badge_dot = self.badge.create_oval(14, 14, 34, 34, fill=MUTED, outline="")
        self.badge_txt = self.badge.create_text(46, 24, text="-", anchor="w", fill=FG, font=(FAMILY, 18, "bold"))
        self.badge.pack(side="left")
        conn = tk.Frame(r1, bg=BG); conn.pack(side="left", padx=16)
        self.dot = tk.Canvas(conn, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot_id = self.dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.dot.pack(side="left")
        self.conn_lbl = self.label(conn, "ESP32" if self.api.connected else "TEST MODE (no ESP32)", fg=MUTED, bg=BG)
        self.conn_lbl.pack(side="left", padx=(6, 0))

        Pill(r1, "STOP", lambda: self.send("stop"), bg=BG, fill=DANGER, fg="#ffffff", size=15, bold=True,
             padx=22, pady=9).pack(side="right")
        Pill(r1, "Resume", lambda: self.send("resume"), bg=BG, padx=14, pady=9).pack(side="right", padx=8)
        # RGB ring on / off (ESP32 'light on|off'; the ESP32 boots with the light ON)
        self.light_seg = Segmented(r1, BG, [(True, "Light ON"), (False, "OFF")], self.set_light, size=11)
        self.light_seg.pack(side="right", padx=10)
        self.light_seg.select(True)
        self.pages = Segmented(r1, BG, [(1, "Monitor"), (2, "Control")], self.show_page)
        self.pages.pack(side="right", padx=18)

        r2 = tk.Frame(top, bg=BG); r2.pack(fill="x", pady=(12, 0))
        self.label(r2, "Emotion", fg=MUTED, bg=BG).pack(side="left", padx=(2, 8))
        self.emo_btn = {}
        b = Pill(r2, "AUTO", lambda: self.force(None), bg=BG, size=11, padx=11, pady=6)
        b.pack(side="left", padx=2); self.emo_btn[None] = b
        for name in EMO_RGB:
            b = Pill(r2, name, lambda n=name: self.force(n), bg=BG, size=11, padx=11, pady=6)
            b.pack(side="left", padx=2); self.emo_btn[name] = b
        self.trial_lbl = self.label(r2, "--:--", fg=MUTED, bg=BG, font=(FAMILY, 12, "bold"))
        self.trial_lbl.pack(side="right", padx=(8, 2))
        Pill(r2, "■ End", lambda: self.send("trial end"), bg=BG, size=11, padx=11, pady=6).pack(side="right", padx=2)
        Pill(r2, "▶ Trial", self.trial_start, bg=BG, size=11, padx=11, pady=6).pack(side="right", padx=2)
        self.cond = Segmented(r2, BG, [(0, "C0"), (1, "C1")], self.set_cond, size=11)
        self.cond.pack(side="right", padx=10)
        self.cond.select(1)
        self.mark_forced()

    def set_light(self, on):
        self.send("light on" if on else "light off")
        self.light_seg.select(on)

    def set_cond(self, k):
        self.send(f"cond {k}")
        self.cond.select(k); self._cond = k     # the D rows confirm it (column cond)

    def force(self, name):
        # AUTO = start / back to automatic: emotions move the robot again and the hormones choose the emotion
        self.send("auto on", "emo auto") if name is None else self.send("auto on", f"emo {name}")
        self.set_auto(True, send=False)
        if not self.api.connected:              # TEST MODE: nobody answers -> show it anyway
            self.forced = name; self.mark_forced()

    def mark_forced(self):
        for k, b in self.emo_btn.items():
            sel = k == self.forced
            if k is None:
                b.style(fill=ACCENT if sel else CARD2, fg="#ffffff" if sel else MUTED)
            else:
                rgb = EMO_RGB[k]
                b.style(fill=hexc(rgb) if sel else blend(rgb, BG, 0.22), fg=text_on(rgb) if sel else FG)

    def trial_start(self):
        # a trial measures the robot as it really runs: Auto ON + emotions from the hormones (not a forced one).
        # Always sent (also when Auto was OFF after boot - otherwise the trial would record a robot that never moves)
        self.force(None)
        self.send("trial start")

    def show_page(self, k):
        self.page = k
        (self.p2 if k == 1 else self.p1).pack_forget()
        (self.p1 if k == 1 else self.p2).pack(fill="both", expand=True)
        self.pages.select(k)
        for g in self.graphs():
            g.dirty = True                      # redraw what was collected while hidden

    def graphs(self):
        return [self.tof[k][2] for k in self.tof] + [g for g, _ in self.h_rows] + [self.cg]

    # ---------------- page 1: monitor ----------------
    def build_page1(self):
        p = tk.Frame(self.body, bg=BG)
        cam = self.card(p, "Camera")
        cam.pack(side="left", fill="y", padx=(0, 12))
        self.cam = tk.Canvas(cam, width=CAM_W, height=CAM_H, bg="#0b0c10", highlightthickness=0)
        self.cam.pack()
        self.cam_wait = self.cam.create_text(CAM_W / 2, CAM_H / 2, text="waiting for the camera ...",
                                             fill="#3a3f4a", font=(FAMILY, 14))
        self.photo = None                       # ONE PhotoImage, new frames are pasted into it
        stats = tk.Frame(cam, bg=CARD); stats.pack(fill="x", pady=(12, 0))
        self.cam_stat = {}
        for i, (key, title) in enumerate((("obj", "Object"), ("person", "Person"), ("wave", "Wave"), ("fps", "fps"))):
            cell = tk.Frame(stats, bg=CARD2, padx=10, pady=8)
            cell.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="nsew")
            stats.columnconfigure(i, weight=1)
            self.label(cell, title, fg=MUTED, bg=CARD2, font=(FAMILY, 10)).pack(anchor="w")
            v = self.label(cell, "-", bg=CARD2, font=(FAMILY, 14, "bold"), width=9, anchor="w"); v.pack(anchor="w")
            self.cam_stat[key] = v

        right = tk.Frame(p, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.tof = {}
        for key, title, marks in (("head", "Head ToF", [(30, "afraid 30"), (10, "jolt 10")]),
                                  ("base", "Base ToF", [(20, "object 20")])):
            f = self.card(right, title)
            f.pack(fill="x", pady=(0, 12))
            row = tk.Frame(f, bg=CARD); row.pack(fill="x")
            big = self.label(row, "-", font=self.f_big, width=8, anchor="w"); big.pack(side="left")
            small = self.label(row, "", fg=MUTED, width=10, anchor="w"); small.pack(side="left", padx=10, pady=(8, 0))
            g = Graph(f, 520, 140, 0, 120, [ACCENT], marks=marks, fill=True)
            g.c.pack(pady=(8, 0))
            self.tof[key] = (big, small, g)
        # motor temperatures (STS only - the MG996R base has no sensor). >= 50 C yellow, >= 58 C red (nap ~58 C)
        t = self.card(right, "Motors  ·  temperature")
        t.pack(fill="x")
        cells = tk.Frame(t, bg=CARD); cells.pack(fill="x")
        self.mtemp = {}
        for i, (title, _, name, _, _) in enumerate([j for j in JOINTS if j[2] != "base"]):
            cell = tk.Frame(cells, bg=CARD2, padx=10, pady=8)
            cell.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="nsew")
            cells.columnconfigure(i, weight=1)
            self.label(cell, title, fg=MUTED, bg=CARD2, font=(FAMILY, 10)).pack(anchor="w")
            v = self.label(cell, "-", bg=CARD2, font=(FAMILY, 16, "bold"), width=7, anchor="w"); v.pack(anchor="w")
            self.mtemp[name] = v
        self.mnap = self.label(t, "", fg=WARN, font=(FAMILY, 12, "bold"))
        self.mnap.pack(anchor="w", pady=(6, 0))
        return p

    # ---------------- page 2: control ----------------
    def build_page2(self):
        p = tk.Frame(self.body, bg=BG)
        left = tk.Frame(p, bg=BG); left.pack(side="left", fill="both", padx=(0, 12))

        h = self.card(left, "Hormone  ·  R")
        h.pack(fill="x", pady=(0, 12))
        self.h_rows = []
        for name, thai, col in HORMONES:
            row = tk.Frame(h, bg=CARD); row.pack(fill="x", pady=2)
            dot = tk.Canvas(row, width=10, height=10, bg=CARD, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=col, outline=""); dot.pack(side="left")
            info = tk.Frame(row, bg=CARD); info.pack(side="left", padx=(8, 4))
            self.label(info, name, width=9, anchor="w").pack(anchor="w")
            self.label(info, f"({thai})", fg=MUTED, font=(FAMILY, 9), anchor="w").pack(anchor="w")
            g = Graph(row, 280, 34, 0, 1, [col], fill=True, grid=False, axis=False)
            g.c.pack(side="left")
            v = self.label(row, "-", font=(FAMILY, 16, "bold"), width=5, anchor="e"); v.pack(side="left", padx=(8, 0))
            self.h_rows.append((g, v))

        c = self.card(left, "CPG  ·  o1 / o2", right=lambda head: self.build_auto(head))
        c.pack(fill="x")
        self.cg = Graph(c, 440, 110, -1, 1, [ACCENT, "#ff9f0a"], n=200)
        self.cg.c.pack()

        m = self.card(p, "Motors", right=lambda head: self.build_tabs(head))
        m.pack(side="left", fill="both", expand=True)
        holder = tk.Frame(m, bg=CARD); holder.pack(fill="both", expand=True)
        self.tab_f = {k: tk.Frame(holder, bg=CARD) for k in ("joints", "cpg", "tof", "cam", "beh")}
        self.build_joints_tab(self.tab_f["joints"])
        self.build_cpg_tab(self.tab_f["cpg"])
        self.build_tof_tab(self.tab_f["tof"])
        self.build_cam_tab(self.tab_f["cam"])
        self.build_groups(self.tab_f["beh"], BEHAV_PARAMS,
                          "person hold: longer = the robot keeps 'seeing' you while you turn away for a moment.\n"
                          "afraid calm: after a fright it stays normal this long (no instant happy again).\n"
                          "sleep after: nobody / nothing seen this long -> sleepy (motors off).\n"
                          "head up: extra head pitch in normal / happy / excited (+ = look up) - set it so the camera sees you standing.")
        self.build_enter_bar(m)
        self.show_tab("joints")
        return p

    def build_auto(self, head):
        self.auto_seg = Segmented(head, CARD, [(True, "Auto ON"), (False, "OFF")], self.set_auto, size=10)
        self.auto_seg.pack(side="right")
        self.auto_seg.select(True)

    def set_auto(self, on, send=True):
        self.auto = on
        self.auto_seg.select(on)
        if send:
            self.send("auto on" if on else "auto off")

    # ---------------- Motors card: tabs Joints | CPG | ToF | Camera + ENTER bar ----------------
    def build_tabs(self, head):
        self.tabs = Segmented(head, CARD, [("joints", "Joints"), ("cpg", "CPG"), ("tof", "ToF"),
                                           ("cam", "Camera"),
                                           ("beh", "Behaviour")], self.show_tab, size=10)
        self.tabs.pack(side="right")

    def show_tab(self, k):
        for f in self.tab_f.values():
            f.pack_forget()
        self.tab_f[k].pack(fill="both", expand=True)
        self.tabs.select(k)

    def add(self, param, **pack):
        param.row.pack(fill="x", **pack)
        self.params.append(param)
        return param

    def build_joints_tab(self, f):
        self.jrow = {}
        for title, thai, name, lo, hi in JOINTS:
            box = tk.Frame(f, bg=CARD2, padx=12, pady=4); box.pack(fill="x", pady=2)
            prm = self.add(Param(self, box, title, thai, 2, lo, hi, "{:+.1f}", "°",
                                 lambda v, n=name: [f"t {n} {v:.1f}"]))
            temp = self.label(prm.slot, "-", bg=CARD2, fg=MUTED, width=6, anchor="e")
            temp.pack(side="right", padx=(10, 0))
            bar = tk.Canvas(box, width=520, height=8, bg=CARD2, highlightthickness=0)    # where it is in its range
            bar.pack(fill="x", pady=(4, 0))
            rrect(bar, 0, 2, 520, 7, 2, fill=LINE, outline="")
            z = (0 - lo) / (hi - lo) * 520
            bar.create_line(z, 0, z, 8, fill=MUTED)                                   # 0 deg mark
            knob = bar.create_oval(0, 0, 8, 8, fill=ACCENT, outline="")
            self.jrow[name] = {"p": prm, "temp": temp, "bar": bar, "knob": knob, "lo": lo, "hi": hi}
        self.nap = self.label(f, "", fg=WARN, font=(FAMILY, 12, "bold"))
        self.nap.pack(anchor="w", pady=(6, 0))

    def build_cpg_tab(self, f):
        box = tk.Frame(f, bg=CARD2, padx=12, pady=8); box.pack(fill="x", pady=3)
        for key, title, thai, step, lo, hi, fmt, unit in CPG_PARAMS:
            if key == "phi":
                cmds = lambda v: ["auto off", f"phi {v:.2f}"]
            else:
                cmds = lambda v, k=key, fm=fmt: [f"tune {k} {fm.format(v)}"]
            prm = self.add(Param(self, box, title, thai, step, lo, hi, fmt, unit, cmds), pady=4)
            if key == "phi":
                self.phi_p = prm
            else:
                self.tune_p[key] = prm
        self.label(f, "phi is set by the hormones while Auto is ON - changing it turns Auto OFF.\n"
                      "alpha / amp × / speed are kept on the ESP32 after Save.",
                   fg=MUTED, font=(FAMILY, 10), justify="left").pack(anchor="w", pady=(6, 0))

    def build_tof_tab(self, f):
        legend = "   ".join(f"{t} ({th})" for _, t, th, *_ in TOF_FIELDS[:2]) + "\n" + \
                 "   ".join(f"{t} ({th})" for _, t, th, *_ in TOF_FIELDS[2:])
        self.label(f, legend, fg=MUTED, font=(FAMILY, 10), justify="left").pack(anchor="w", pady=(0, 4))
        for name, title, thai in TOF_GROUPS:
            g = tk.Frame(f, bg=CARD2, padx=12, pady=3); g.pack(fill="x", pady=2)
            head = tk.Frame(g, bg=CARD2); head.pack(fill="x")
            self.label(head, title, bg=CARD2, font=(FAMILY, 11, "bold")).pack(side="left")
            self.label(head, f"({thai})", bg=CARD2, fg=MUTED, font=(FAMILY, 10)).pack(side="left", padx=6)
            grid = tk.Frame(g, bg=CARD2); grid.pack(fill="x", pady=(1, 0))
            for i, (field, ftitle, fthai, step, lo, hi, fmt, unit) in enumerate(TOF_FIELDS):
                key = f"{name}.{field}"
                prm = Param(self, grid, ftitle, None, step, lo, hi, fmt, unit,
                            lambda v, k=key, fm=fmt: [f"tune {k} {fm.format(v)}"], title_w=6, now_w=6, compact=True)
                prm.row.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 16) if i % 2 == 0 else 0, pady=1)
                self.params.append(prm)
                self.tune_p[key] = prm

    def build_cam_tab(self, f):
        for title, thai, items in CAM_PARAMS:
            g = tk.Frame(f, bg=CARD2, padx=12, pady=6); g.pack(fill="x", pady=3)
            head = tk.Frame(g, bg=CARD2); head.pack(fill="x", pady=(0, 2))
            self.label(head, title, bg=CARD2, font=(FAMILY, 11, "bold")).pack(side="left")
            self.label(head, f"({thai})", bg=CARD2, fg=MUTED, font=(FAMILY, 10)).pack(side="left", padx=6)
            for key, ptitle, pthai, step, lo, hi, fmt, unit in items:
                prm = self.add(Param(self, g, ptitle, pthai, step, lo, hi, fmt, unit,
                                     lambda v, k=key, fm=fmt: [f"{k} {fm.format(v)}" if k.startswith("cam:")
                                                               else f"tune {k} {fm.format(v)}"], title_w=11), pady=3)
                self.tune_p[key] = prm
        self.label(f, "conf: lower = finds more but more mistakes, higher = sure but may lose it.\n"
                      "track speed too high -> the head shakes and the camera image blurs.\n"
                      "Camera-program values are saved on the laptop; ESP32 values with Save.\n"
                      "track start: 1 = follow every small move, 10 = only when it is clearly off centre, 0 = never.\n"
                      "% = part of the image width from the centre (stop is never bigger than start).",
                   fg=MUTED, font=(FAMILY, 10), justify="left").pack(anchor="w", pady=(6, 0))

    def build_groups(self, f, groups, note=""):
        """tab made of value groups (ESP32 tune keys)"""
        for title, thai, items in groups:
            g = tk.Frame(f, bg=CARD2, padx=12, pady=6); g.pack(fill="x", pady=3)
            head = tk.Frame(g, bg=CARD2); head.pack(fill="x", pady=(0, 2))
            self.label(head, title, bg=CARD2, font=(FAMILY, 11, "bold")).pack(side="left")
            self.label(head, f"({thai})", bg=CARD2, fg=MUTED, font=(FAMILY, 10)).pack(side="left", padx=6)
            for key, ptitle, pthai, step, lo, hi, fmt, unit in items:
                self.tune_p[key] = self.add(Param(self, g, ptitle, pthai, step, lo, hi, fmt, unit,
                                                  lambda v, k=key, fm=fmt: [f"tune {k} {fm.format(v)}"], title_w=11),
                                            pady=3)
        if note:
            self.label(f, note, fg=MUTED, font=(FAMILY, 10), justify="left").pack(anchor="w", pady=(6, 0))

    def cam_set(self, c):
        """camera-program setting (laptop side) - never goes to the ESP32"""
        key, v = c.split()
        self.api.set_cam(key, float(v))
        self.tune_p[key].set_now(self.api.cam_settings()[key])
        self.log(f"camera: {key[4:]} = {v}")

    def build_enter_bar(self, parent):
        bar = tk.Frame(parent, bg=CARD); bar.pack(fill="x", pady=(10, 0))
        Pill(bar, "ENTER ⏎", self.apply, bg=CARD, fill=ACCENT, fg="#ffffff", size=13, bold=True,
             padx=20, pady=7).pack(side="left")
        self.pending_lbl = self.label(bar, "no changes", fg=MUTED, width=16, anchor="w")
        self.pending_lbl.pack(side="left", padx=10)
        Pill(bar, "Reset", self.reset, bg=CARD, size=11, padx=12, pady=6).pack(side="right")
        Pill(bar, "Save", self.save, bg=CARD, size=11, padx=12, pady=6).pack(side="right", padx=6)
        self.saved_lbl = self.label(bar, "", fg=MUTED, font=(FAMILY, 10))
        self.saved_lbl.pack(side="right", padx=6)

    def count_pending(self):
        n = sum(p.pending for p in self.params)
        put(self.pending_lbl, "no changes" if n == 0 else f"{n} change{'s' if n > 1 else ''} - press ENTER")

    def apply(self):
        """ENTER: send every changed value at once"""
        cmds = []
        for p in self.params:
            for c in p.take():
                if c not in cmds:
                    cmds.append(c)
        if any(c.startswith(("t ", "phi")) for c in cmds):
            self.set_auto(False, send=False)    # 't' and phi need Auto OFF (t does it on the ESP32 itself)
        for c in cmds:
            self.cam_set(c) if c.startswith("cam:") else self.send(c)
        self.count_pending()
        self.root.focus_set()                   # leave the box

    def save(self):
        self.send("tune save")                  # ESP32 values -> its Preferences
        self.api.save_cam()
        self.log("camera: settings saved on the laptop (camera/settings.json)")

    def reset(self):
        if messagebox.askyesno("Reset", "Erase the values saved on the ESP32 and go back to the TUNING defaults?"):
            self.send("tune reset")

    # ---------------- bottom: log + command ----------------
    def build_bottom(self):
        b = tk.Frame(self.root, bg=CARD, padx=12, pady=10)
        b.pack(fill="x", padx=16, pady=(0, 14))
        self.logbox = tk.Text(b, height=4, font=("Menlo", 11), bg=CARD, fg=MUTED, relief="flat",
                              highlightthickness=0, state="disabled", wrap="none")
        self.logbox.pack(fill="x")
        row = tk.Frame(b, bg=CARD); row.pack(fill="x", pady=(8, 0))
        self.label(row, "›", fg=ACCENT, font=(FAMILY, 18, "bold")).pack(side="left")
        self.cmd = tk.Entry(row, font=("Menlo", 12), bg=CARD2, fg=FG, insertbackground=FG, relief="flat",
                            highlightthickness=1, highlightbackground=CARD2, highlightcolor=ACCENT)
        self.cmd.pack(side="left", fill="x", expand=True, padx=8, ipady=5)
        self.cmd.bind("<Return>", lambda e: (self.send(self.cmd.get().strip()), self.cmd.delete(0, "end")))
        if getattr(self.api, "web_url", ""):
            self.label(row, f"iPad: {self.api.web_url}", fg=MUTED, font=(FAMILY, 10)).pack(side="right")

    # ---------------- refresh ----------------
    def line_tick(self):
        """ESP32 lines (not D / E): read the whole queue, then come back"""
        if getattr(self.api, "stopping", lambda: False)():   # Ctrl+C in the terminal
            self.close()
            return
        q = self.api.lines
        for _ in range(200):
            if q.empty():
                break
            self.on_line(q.get_nowait())
        self.root.after(50, self.line_tick)

    def graph_tick(self):
        n, _, d = self.api.latest_d()
        if n != self.d_seen:                    # a point only for a NEW D row (no fake scrolling)
            self.d_seen, self.d = n, d
            for key in ("base", "head"):
                ok = d.get(f"{key}_ok") == "1"
                self.tof[key][2].push(num(d, f"{key}_f") if ok else None)
            for (g, _), (name, _, _) in zip(self.h_rows, HORMONES):
                g.push(num(d, f"{name}_R"))
            self.cg.push(num(d, "o1"), num(d, "o2"))
        if self.page == 1:                      # only the visible page is drawn
            for key in ("base", "head"):
                self.tof[key][2].draw()
        else:
            for g, _ in self.h_rows:
                g.draw()
            self.cg.draw()
        self.root.after(GRAPH_MS, self.graph_tick)

    def text_tick(self):
        d = self.d
        _, t_d, _ = self.api.latest_d()
        link = self.api.connected and t_d is not None and time.monotonic() - t_d < LINK_TIMEOUT_S
        # no D rows (ESP32 restarted, or opened without a restart and missed the first commands): ask again every 3 s
        if self.api.connected and not link and time.monotonic() - getattr(self, "_hello_t", 0) > HELLO_S:
            self._hello_t = time.monotonic()
            self.hello()
        col = OK if link else (DANGER if self.api.connected else MUTED)
        if self.dot.itemcget(self.dot_id, "fill") != col:
            self.dot.itemconfigure(self.dot_id, fill=col)
        ts = num(d, "trial_s")
        put(self.trial_lbl, "--:--" if ts is None or ts < 0 else f"{int(ts) // 60:02d}:{int(ts) % 60:02d}",
            FG if ts is not None and ts >= 0 else MUTED)
        if d.get("auto") in ("0", "1") and (d["auto"] == "1") != self.auto:   # the ESP32 says (after boot: OFF)
            self.set_auto(d["auto"] == "1", send=False)
        if d.get("cond") in ("0", "1"):
            k = int(d["cond"])
            if getattr(self, "_cond", None) != k:
                self._cond = k; self.cond.select(k)
        emo = d.get("emotion", "")
        badge = (emo.upper() if emo else "-") + ("   FORCED" if self.forced else "")
        if badge != self.badge.itemcget(self.badge_txt, "text"):
            rgb = EMO_RGB.get(emo, rgb_of(MUTED))
            self.badge.itemconfigure(self.badge_bg, fill=blend(rgb, BG, 0.25))
            self.badge.itemconfigure(self.badge_dot, fill=hexc(rgb))
            self.badge.itemconfigure(self.badge_txt, text=badge)
        cam = self.api.cam()
        if self.page == 1:
            put(self.cam_stat["obj"], f"{cam['obj_name']} · {cam['obj_id']}" if cam.get("obj_name") else "-")
            put(self.cam_stat["person"], "Yes" if cam.get("person") else "No", OK if cam.get("person") else MUTED)
            waving = time.time() < cam.get("wave_until", 0)
            put(self.cam_stat["wave"], "Waving!" if waving else f"{cam.get('waves', 0)} times", WARN if waving else FG)
            put(self.cam_stat["fps"], f"{cam.get('fps', 0):.1f}")
            for key in ("base", "head"):
                big, small, _ = self.tof[key]
                ok, f, r = d.get(f"{key}_ok"), num(d, f"{key}_f"), num(d, f"{key}_raw")
                if not d:
                    put(big, "-", MUTED); put(small, "")
                elif ok != "1" or f is None:
                    put(big, "invalid", MUTED); put(small, "")
                else:
                    put(big, f"{f:.1f} cm", FG); put(small, "" if r is None else f"raw {r:.1f}")
        for k, v in self.api.cam_settings().items():    # may be changed from the iPad page
            self.tune_p[k].set_now(v)
        # 'now' of phi / joints: ALWAYS kept up to date (so - / + work at once after switching page);
        # set_now() does nothing when the value did not change
        self.phi_p.set_now(num(d, "phi"))
        for name, j in self.jrow.items():
            v = num(d, f"{name}_cmd")
            if j["p"].now != v:
                j["p"].set_now(v)
                if v is not None:
                    x = (v - j["lo"]) / (j["hi"] - j["lo"]) * 512
                    j["bar"].coords(j["knob"], x, 0, x + 8, 8)
        if self.page == 1:
            for name, lbl in self.mtemp.items():
                tc = num(d, f"{name}_temp")
                if tc is None:
                    put(lbl, "-", MUTED)
                else:
                    put(lbl, f"{tc:.0f} °C", DANGER if tc >= 58 else WARN if tc >= 50 else FG)
            put(self.mnap, "Resting - cooling motors" if d.get("napping") == "1" else "")
        if self.page == 2:
            for (_, lbl), (name, _, _) in zip(self.h_rows, HORMONES):
                v = num(d, f"{name}_R")
                put(lbl, "-" if v is None else f"{v:.2f}")
            for name, j in self.jrow.items():
                tc = num(d, f"{name}_temp")
                if tc is None:
                    put(j["temp"], "-", MUTED)
                else:
                    put(j["temp"], f"{tc:.0f} °C", DANGER if tc >= 58 else WARN if tc >= 50 else MUTED)
            put(self.nap, "Resting - cooling motors" if d.get("napping") == "1" else "")
        self.root.after(TEXT_MS, self.text_tick)

    def cam_tick(self):
        if self.page == 1:
            rgb = self.api.cam().get("rgb")     # already 480x360 RGB (made in the camera thread)
            if rgb is not None and rgb is not getattr(self, "_last_rgb", None):
                self._last_rgb = rgb
                img = Image.fromarray(rgb)
                if self.photo is None:
                    self.photo = ImageTk.PhotoImage(img)
                    self.cam.create_image(0, 0, image=self.photo, anchor="nw")
                    self.cam.delete(self.cam_wait)
                else:
                    self.photo.paste(img)
        self.root.after(CAM_MS, self.cam_tick)


def run(api):
    root = tk.Tk()
    App(root, api)
    root.mainloop()
