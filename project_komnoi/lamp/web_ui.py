"""เว็บแดชบอร์ดของโคม -- ใช้แค่ Python standard library (เครื่องที่ไม่มีอะไรเลยก็รันได้)

sensor_bridge.py เปิดให้เอง: http://localhost:8080
  GET  /        -> dashboard.html (ไฟล์ข้างๆ ไฟล์นี้)
  GET  /state   -> JSON สถานะล่าสุด + ประวัติฮอร์โมน 2 นาที
  POST /cmd     -> {"cmd": "key", "key": "1"} | {"cmd": "dip"} | {"cmd": "reset"}
คำสั่งจากเว็บเข้าคิว แล้วลูปหลักของ sensor_bridge ดึงไปทำ (ไม่แตะสมองจากเธรดอื่น)
"""
import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_S = 120.0
SAMPLE_S = 0.5


class WebUI:
    def __init__(self, host="127.0.0.1", port=8080):
        self.host, self.port = host, port
        self.lock = threading.Lock()
        self.snapshot = {}
        self.history = []                  # [t, state, cau, cur, aff, slp, sick]
        self._last_sample = -1e9
        self.cmds = queue.Queue()
        self.server = None

    # ---------------------------------------------------------------- ฝั่งลูปหลัก
    def start(self):
        ui = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):     # เงียบ ไม่พิมพ์ทุกคำขอ
                pass

            def _send(self, code, body, ctype):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    try:
                        with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                            body = f.read()
                    except OSError:
                        body = "ไม่พบ dashboard.html (ต้องอยู่โฟลเดอร์เดียวกับ web_ui.py)".encode("utf-8")
                    self._send(200, body, "text/html; charset=utf-8")
                elif self.path.startswith("/state"):
                    with ui.lock:
                        data = dict(ui.snapshot, history=list(ui.history))
                    self._send(200, json.dumps(data).encode("utf-8"), "application/json")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self):
                if self.path != "/cmd":
                    self._send(404, b"not found", "text/plain")
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    msg = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                    cmd = msg.get("cmd")
                    if cmd == "key" and str(msg.get("key")) in "123456789" and len(str(msg.get("key"))) == 1:
                        ui.cmds.put(("key", str(msg["key"])))
                    elif cmd in ("dip", "reset"):
                        ui.cmds.put((cmd, None))
                    else:
                        raise ValueError("unknown command")
                    self._send(200, b'{"ok": true}', "application/json")
                except Exception as e:
                    self._send(400, json.dumps({"ok": False, "error": str(e)}).encode("utf-8"),
                               "application/json")

        try:
            self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            print("เปิดเว็บไม่ได้ (พอร์ต %d ไม่ว่าง?): %s" % (self.port, e))
            return None
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        shown = "localhost" if self.host in ("127.0.0.1", "0.0.0.0") else self.host
        return "http://%s:%d" % (shown, self.port)

    def push(self, now, snap):
        """ลูปหลักเรียกทุกรอบสมอง (10 Hz) ; เก็บประวัติทุก SAMPLE_S"""
        with self.lock:
            self.snapshot = snap
            if now - self._last_sample >= SAMPLE_S:
                self._last_sample = now
                H = snap.get("H", {})
                self.history.append([round(snap.get("t", 0.0), 2), snap.get("state"),
                                     round(H.get("caution", 0.0), 3), round(H.get("curiosity", 0.0), 3),
                                     round(H.get("affinity", 0.0), 3), round(H.get("sleepiness", 0.0), 3),
                                     round(H.get("sickness", 0.0), 3)])
                t_cut = snap.get("t", 0.0) - HISTORY_S
                while self.history and self.history[0][0] < t_cut:
                    self.history.pop(0)

    def commands(self):
        out = []
        while True:
            try:
                out.append(self.cmds.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
