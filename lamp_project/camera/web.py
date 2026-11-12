"""web.py - the GUI on an iPad / phone (same WiFi as the laptop). Started by lamp_camera.py.

The same as the desktop GUI: top bar (emotion, STOP, emotion buttons, C0/C1, trial), Monitor (camera picture + ToF
graphs), Control (hormone graphs, CPG graph + Auto, Motors card: Joints | CPG | ToF | Camera), log + command box.
How it stays light:
  - the page asks for /state 5 times a second and gets only what is NEW (new D rows, new log lines) - it draws the
    graphs itself; /cam.jpg is fetched ~7 times a second ONLY while the Monitor page is visible
  - the laptop encodes a JPEG only when asked and only once per new camera picture
  - one small Python thread (standard library http.server)
Safety: the link has a PIN (random once, kept in settings.json); without it nothing is answered.
"""
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from gui import (JOINTS, CPG_PARAMS, TOF_GROUPS, TOF_FIELDS, CAM_PARAMS, BEHAV_PARAMS, EMO_RGB, HORMONES)  # ONE list for both


def page_params():
    """the rows of each Motors tab, as plain data for the page"""
    def row(key, title, thai, step, lo, hi, fmt, unit):
        return {"key": key, "title": title, "thai": thai, "step": step, "lo": lo, "hi": hi, "dec": dec(fmt), "unit": unit}
    return [
        ("Joints", [{"title": "", "thai": "", "rows": [row(f"j:{n}", t, th, 2, lo, hi, "{:+.1f}", "°")
                                                       for t, th, n, lo, hi in JOINTS]}]),
        ("CPG", [{"title": "", "thai": "", "rows": [row(*p) for p in CPG_PARAMS]}]),
        ("ToF", [{"title": gt, "thai": gth, "rows": [row(f"{g}.{f}", t, th, st, lo, hi, fm, u)
                                                     for f, t, th, st, lo, hi, fm, u in TOF_FIELDS]}
                 for g, gt, gth in TOF_GROUPS]),
        ("Camera", [{"title": gt, "thai": gth, "rows": [row(*p) for p in items]} for gt, gth, items in CAM_PARAMS]),
        ("Behaviour", [{"title": gt, "thai": gth, "rows": [row(*p) for p in items]} for gt, gth, items in BEHAV_PARAMS]),
    ]


def dec(fmt):
    m = re.search(r"\.(\d)f", fmt)
    return int(m.group(1)) if m else 0


def lan_ip():
    """the laptop's address on the WiFi (no packet is sent)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def start(api, port, pin):
    """api: state(since_d, since_log) -> dict, jpeg() -> bytes, run(cmd) -> error or None. Returns the URL."""
    consts = {"tabs": page_params(), "emo": {k: "#%02x%02x%02x" % v for k, v in EMO_RGB.items()},
              "hormones": [[n, th, c] for n, th, c in HORMONES]}
    html = PAGE.replace("__CONSTS__", json.dumps(consts, ensure_ascii=False))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):          # quiet (no line per request in the terminal)
            pass

        def query(self):
            return parse_qs(urlparse(self.path).query)

        def ok_pin(self):
            if self.query().get("pin", [""])[0] == pin:
                return True
            self.reply(403, "text/plain", b"wrong or missing PIN - open the link printed by the camera program")
            return False

        def reply(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.ok_pin():
                return
            path, q = urlparse(self.path).path, self.query()
            if path == "/":
                self.reply(200, "text/html; charset=utf-8", html.encode())
            elif path == "/state":
                try:
                    sd, sl = int(q.get("d", ["0"])[0]), int(q.get("l", ["0"])[0])
                except ValueError:
                    sd = sl = 0
                self.reply(200, "application/json", json.dumps(api.state(sd, sl), separators=(",", ":")).encode())
            elif path == "/cam.jpg":
                jpg = api.jpeg()
                self.reply(200 if jpg else 204, "image/jpeg", jpg)
            else:
                self.reply(404, "text/plain", b"not found")

        def do_POST(self):
            if not self.ok_pin():
                return
            if urlparse(self.path).path != "/cmd":
                return self.reply(404, "text/plain", b"not found")
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 10000)
                cmds = json.loads(self.rfile.read(n)).get("cmds", [])[:60]
            except (ValueError, AttributeError):
                return self.reply(400, "text/plain", b"bad request")
            errors = []
            for c in cmds:
                c = str(c).strip().lower()
                # any ESP32 command (like the GUI command box) - but never fake camera data, never junk
                if not c or len(c) > 80 or not c.isprintable() or c.startswith(("cam,", "wave,")):
                    errors.append(f"refused: {c[:40]}")
                    continue
                e = api.run(c)
                if e:
                    errors.append(e)
            self.reply(200, "application/json", json.dumps({"errors": errors}).encode())

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://{lan_ip()}:{port}/?pin={pin}"


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Lamp Robot</title>
<style>
:root { --bg:#121419; --card:#1b1e25; --card2:#262a33; --line:#2e333d; --fg:#e8eaed; --muted:#8b919c;
        --accent:#4c8dff; --ok:#34c759; --warn:#f5b942; --danger:#ff453a; }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px -apple-system, "Helvetica Neue", sans-serif; padding:12px; }
button { font:inherit; border:0; border-radius:999px; padding:8px 14px; background:var(--card2); color:var(--fg);
         touch-action:manipulation; cursor:pointer; }
button:active { filter:brightness(1.35); }
.seg button { color:var(--muted); } .seg button.on { background:var(--accent); color:#fff; }
.top, .row2 { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.row2 { margin:10px 0; }
.badge { display:flex; align-items:center; gap:10px; background:var(--card); border-radius:24px; padding:8px 18px 8px 10px;
         font-size:20px; font-weight:700; min-width:250px; }
.badge i { width:20px; height:20px; border-radius:50%; background:var(--muted); display:inline-block; }
.dot { width:10px; height:10px; border-radius:50%; background:var(--muted); display:inline-block; margin-right:4px; }
#conn { color:var(--muted); font-size:13px; }
.sp { flex:1; }
.stop { background:var(--danger); color:#fff; font-weight:700; font-size:18px; padding:10px 24px; }
.emo button { padding:6px 11px; font-size:14px; }
#trial { color:var(--muted); font-weight:700; min-width:48px; }
.grid { display:grid; grid-template-columns: minmax(300px, 520px) 1fr; gap:12px; }
@media (max-width:900px) { .grid { grid-template-columns:1fr; } }
.card { background:var(--card); border-radius:14px; padding:12px 14px; margin-bottom:12px; }
.ctitle { color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
          display:flex; align-items:center; gap:8px; margin-bottom:8px; }
#camimg { width:100%; aspect-ratio:4/3; background:#0b0c10; border-radius:8px; display:block; object-fit:contain; }
.stats { display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; margin-top:10px; }
.stat { background:var(--card2); border-radius:10px; padding:8px 10px; }
.stat small { color:var(--muted); display:block; font-size:12px; } .stat b { font-size:16px; }
.big { font-size:26px; font-weight:700; } .muted { color:var(--muted); }
canvas { width:100%; display:block; }
.hrow { display:flex; align-items:center; gap:8px; padding:3px 0; }
.hrow .n { width:96px; } .hrow .n small { color:var(--muted); display:block; font-size:11px; }
.hrow canvas { flex:1; height:34px; } .hrow b { width:46px; text-align:right; font-size:17px; }
.tabs { margin-left:auto; display:flex; gap:2px; }
.group { background:var(--card2); border-radius:10px; padding:8px 12px; margin-bottom:6px; }
.gtitle { font-weight:700; font-size:14px; margin-bottom:2px; } .gtitle span { color:var(--muted); font-weight:400; font-size:12px; }
.prow { display:flex; align-items:center; gap:6px; padding:5px 0; }
.prow .name { flex:1; min-width:0; } .prow .name b { display:block; } .prow .name small { color:var(--muted); font-size:12px; }
.now { color:var(--muted); font-size:12px; text-align:right; min-width:84px; } .now b { color:var(--fg); font-size:16px; }
.temp { width:52px; text-align:right; font-size:13px; color:var(--muted); }
.pm { width:40px; height:40px; padding:0; font-size:20px; background:var(--line); }
input { height:40px; border-radius:10px; border:1px solid var(--line); background:var(--bg); color:var(--fg);
        font:inherit; text-align:center; width:72px; }
input:focus { outline:none; border-color:var(--accent); }
.enterbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px; }
.enter { background:var(--accent); color:#fff; font-weight:700; padding:10px 22px; }
#pending { color:var(--muted); font-size:13px; margin-right:auto; } #saved { font-size:12px; color:var(--muted); }
#nap { color:var(--warn); font-weight:700; }
#log { height:96px; overflow-y:auto; font:12px Menlo, monospace; color:var(--muted); white-space:pre; }
.cmdrow { display:flex; gap:8px; margin-top:8px; } .cmdrow input { flex:1; text-align:left; padding:0 10px; font-family:Menlo, monospace; }
#msg { color:var(--danger); font-size:12px; }
</style></head><body>
<div class="top">
  <div class="badge"><i id="bdot"></i><span id="btxt">-</span></div>
  <span id="conn"><span class="dot" id="cdot"></span><span id="ctxt">connecting...</span></span>
  <span class="sp"></span>
  <span class="seg" id="pages"><button data-p="0">Monitor</button><button data-p="1">Control</button></span>
  <span class="seg" id="light"><button data-l="1" class="on">Light ON</button><button data-l="0">OFF</button></span>
  <button onclick="send(['resume'])">Resume</button>
  <button class="stop" onclick="send(['stop'])">STOP</button>
</div>
<div class="row2">
  <span class="muted">Emotion</span><span class="emo seg" id="emo"></span>
  <span class="sp"></span>
  <span class="seg" id="cond"><button data-c="0">C0</button><button data-c="1">C1</button></span>
  <button onclick="trialStart()">▶ Trial</button><button onclick="send(['trial end'])">■ End</button>
  <span id="trial">--:--</span>
</div>

<div id="page0" class="grid">
  <div class="card"><div class="ctitle">Camera</div>
    <img id="camimg" alt="">
    <div class="stats">
      <div class="stat"><small>Object</small><b id="s_obj">-</b></div>
      <div class="stat"><small>Person</small><b id="s_person">-</b></div>
      <div class="stat"><small>Wave</small><b id="s_wave">-</b></div>
      <div class="stat"><small>fps</small><b id="s_fps">-</b></div>
    </div></div>
  <div>
    <div class="card"><div class="ctitle">Head ToF</div><span class="big" id="t_head">-</span> <span class="muted" id="t_head_raw"></span>
      <canvas id="g_head" height="140"></canvas></div>
    <div class="card"><div class="ctitle">Base ToF</div><span class="big" id="t_base">-</span> <span class="muted" id="t_base_raw"></span>
      <canvas id="g_base" height="140"></canvas></div>
    <div class="card"><div class="ctitle">Motors · temperature</div>
      <div class="stats">
        <div class="stat"><small>Shoulder</small><b id="mtemp_shoulder">-</b></div>
        <div class="stat"><small>Elbow</small><b id="mtemp_elbow">-</b></div>
        <div class="stat"><small>Head pitch</small><b id="mtemp_pitch">-</b></div>
        <div class="stat"><small>Head yaw</small><b id="mtemp_yaw">-</b></div>
      </div><div class="muted" id="mnap" style="color:#f5b942"></div></div>
  </div>
</div>

<div id="page1" class="grid" style="display:none">
  <div>
    <div class="card"><div class="ctitle">Hormone · R</div><div id="hrows"></div></div>
    <div class="card"><div class="ctitle">CPG · o1 / o2 <span class="seg tabs" id="auto"><button data-a="1">Auto ON</button><button data-a="0">OFF</button></span></div>
      <canvas id="g_cpg" height="110"></canvas></div>
  </div>
  <div class="card"><div class="ctitle">Motors <span class="seg tabs" id="tabs"></span></div>
    <div id="tabbody"></div><div id="nap"></div>
    <div class="enterbar">
      <button class="enter" onclick="enter()">ENTER ⏎</button><span id="pending">no changes</span>
      <span id="saved"></span>
      <button onclick="send(['tune save','camsave'])">Save</button>
      <button onclick="if (confirm('Erase the values saved on the ESP32 and go back to the TUNING defaults?')) send(['tune reset'])">Reset</button>
    </div>
  </div>
</div>

<div class="card"><div id="log"></div>
  <div class="cmdrow"><input id="cmd" placeholder="command (h = list)" autocomplete="off" autocapitalize="none"><button onclick="sendTyped()">Send</button></div>
  <div id="msg"></div></div>

<script>
const C = __CONSTS__;
const PIN = new URLSearchParams(location.search).get("pin") || "";
const N = 600;                                    // 30 s at 20 rows/s
const hist = {base: [], head: [], h: [[], [], [], [], []], o1: [], o2: []};
let page = 0, mtab = 0, dSeq = 0, lSeq = 0, S = null;
const rows = {};                                  // key -> {def, now, pending, input, nowEl}
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));

// ---------- build ----------
function seg(el, attr, onpick) { el.querySelectorAll("button").forEach(b => b.onclick = () => onpick(b.dataset[attr])); }
function mark(el, attr, val) { el.querySelectorAll("button").forEach(b => b.className = b.dataset[attr] === String(val) ? "on" : ""); }
function build() {
  seg($("pages"), "p", p => showPage(+p));
  seg($("cond"), "c", c => { send([`cond ${c}`]); mark($("cond"), "c", c); });
  seg($("light"), "l", l => { send([l === "1" ? "light on" : "light off"]); mark($("light"), "l", l); });   // RGB ring
  seg($("auto"), "a", a => send([a === "1" ? "auto on" : "auto off"]));
  const emo = $("emo");
  const auto = document.createElement("button"); auto.textContent = "AUTO"; auto.dataset.e = "";
  auto.onclick = () => send(["auto on", "emo auto"]); emo.appendChild(auto);
  for (const [name, col] of Object.entries(C.emo)) {
    const b = document.createElement("button"); b.textContent = name; b.dataset.e = name; b.dataset.col = col;
    b.onclick = () => send(["auto on", `emo ${name}`]); emo.appendChild(b);
  }
  $("hrows").innerHTML = C.hormones.map(([n, th, col], i) =>
    `<div class="hrow"><i class="dot" style="background:${col}"></i><div class="n">${n}<small>(${th})</small></div>` +
    `<canvas id="g_h${i}" height="34"></canvas><b id="h${i}">-</b></div>`).join("");
  const tabs = $("tabs"), body = $("tabbody");
  C.tabs.forEach(([name, groups], i) => {
    const b = document.createElement("button"); b.textContent = name; b.dataset.t = i; tabs.appendChild(b);
    const pg = document.createElement("div"); pg.className = "mtab"; pg.style.display = "none";
    groups.forEach(g => {
      const box = document.createElement("div"); box.className = "group";
      if (g.title) box.innerHTML = `<div class="gtitle">${g.title} <span>(${g.thai})</span></div>`;
      g.rows.forEach(r => {
        const row = document.createElement("div"); row.className = "prow";
        row.innerHTML = `<div class="name"><b>${r.title}</b><small>(${r.thai})</small></div>` +
          `<div class="now">now <b>-</b></div><button class="pm">−</button><input inputmode="decimal" autocomplete="off">` +
          `<button class="pm">+</button>` + (r.key.startsWith("j:") ? `<span class="temp" id="temp_${r.key.slice(2)}">-</span>` : "");
        const [minus, plus] = row.querySelectorAll(".pm"), input = row.querySelector("input");
        const st = rows[r.key] = {def: r, now: null, pending: false, input, nowEl: row.querySelector(".now b")};
        minus.onclick = () => step(st, -1); plus.onclick = () => step(st, +1);
        input.oninput = () => touch(st);
        input.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); input.blur(); enter(); } };
        box.appendChild(row);
      });
      pg.appendChild(box);
    });
    body.appendChild(pg);
  });
  seg(tabs, "t", t => showTab(+t));
  $("cmd").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); sendTyped(); } };
  const q = new URLSearchParams(location.search);          // ?page=1&tab=2 opens that page / Motors tab
  showPage(+(q.get("page") || 0) === 1 ? 1 : 0); showTab(Math.min(Math.max(+(q.get("tab") || 0), 0), C.tabs.length - 1));
}
function showPage(p) { page = p; $("page0").style.display = p === 0 ? "" : "none"; $("page1").style.display = p === 1 ? "" : "none";
                       mark($("pages"), "p", p); drawAll(); }
function showTab(t) { mtab = t; document.querySelectorAll(".mtab").forEach((x, k) => x.style.display = k === t ? "" : "none");
                      mark($("tabs"), "t", t); }

// ---------- value rows (same rules as the desktop: - / + / typing only edit the box, ENTER sends) ----------
const fmt = (r, v) => Number(v).toFixed(r.dec);
const clamp = (r, v) => Math.min(Math.max(v, r.lo), r.hi);
function step(st, d) {
  const r = st.def; let base = parseFloat(st.input.value);
  if (isNaN(base)) base = st.now; if (base === null || isNaN(base)) return;
  st.input.value = fmt(r, clamp(r, Math.round((base + d * r.step) / r.step) * r.step)); touch(st);
}
function touch(st) {
  st.pending = st.input.value.trim() !== (st.now === null ? "" : fmt(st.def, st.now));
  const n = Object.values(rows).filter(s => s.pending).length;
  $("pending").textContent = n ? `${n} change${n > 1 ? "s" : ""} - press ENTER` : "no changes";
}
function cmdsFor(key, r, v) {
  const t = fmt(r, v);
  if (key.startsWith("j:")) return [`t ${key.slice(2)} ${t}`];
  if (key === "phi") return ["auto off", `phi ${t}`];
  if (key.startsWith("cam:")) return [`${key} ${t}`];
  return [`tune ${key} ${t}`];
}
function enter() {
  const cmds = [];
  for (const [key, st] of Object.entries(rows)) {
    if (!st.pending) continue;
    const v = parseFloat(st.input.value); st.pending = false;
    if (isNaN(v)) { if (st.now !== null) st.input.value = fmt(st.def, st.now); continue; }
    for (const c of cmdsFor(key, st.def, clamp(st.def, v))) if (!cmds.includes(c)) cmds.push(c);
  }
  touch(Object.values(rows)[0]);
  if (cmds.length) send(cmds);
}
function trialStart() { send(["auto on", "emo auto", "trial start"]); }   // trial = real run: Auto ON + hormones
function sendTyped() { const c = $("cmd").value.trim(); if (c) { send([c]); $("cmd").value = ""; } }
async function send(cmds) {
  try {
    const r = await fetch(`/cmd?pin=${PIN}`, {method: "POST", headers: {"Content-Type": "application/json"},
                                              body: JSON.stringify({cmds})});
    $("msg").textContent = ((await r.json()).errors || []).join("  ");
  } catch (e) { $("msg").textContent = "cannot reach the laptop"; }
}

// ---------- graphs (canvas, redrawn only when new data came and only on the visible page) ----------
function push(a, v, n) { a.push(v); if (a.length > n) a.splice(0, a.length - n); }
function graph(id, series, lo, hi, n, marks, fill) {
  const cv = $(id); if (!cv || cv.offsetParent === null) return;
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth;
  const h = +(cv.dataset.h || (cv.dataset.h = cv.getAttribute("height")));   // CSS height, read ONCE (cv.height becomes h * dpr)
  if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + "px"; }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const y = v => h - 3 - (Math.min(Math.max(v, lo), hi) - lo) / (hi - lo) * (h - 6), dx = (w - 1) / (n - 1);
  if (fill === undefined) { g.strokeStyle = "#2e333d"; g.lineWidth = 1; for (let k = 1; k < 4; k++) { g.beginPath(); g.moveTo(0, h * k / 4); g.lineTo(w, h * k / 4); g.stroke(); } }
  g.font = "10px -apple-system"; g.fillStyle = "#8b919c";
  for (const [v, label] of (marks || [])) { g.setLineDash([3, 4]); g.strokeStyle = "#8b919c"; g.beginPath(); g.moveTo(0, y(v)); g.lineTo(w, y(v)); g.stroke();
                                            g.setLineDash([]); g.textAlign = "right"; g.fillText(label, w - 4, y(v) - 4); }
  for (const [a, col] of series) {
    const off = n - a.length; g.strokeStyle = col; g.lineWidth = 2; g.beginPath(); let pen = false;
    a.forEach((v, i) => { if (v === null) { pen = false; return; } const X = (off + i) * dx, Y = y(v); pen ? g.lineTo(X, Y) : g.moveTo(X, Y); pen = true; });
    g.stroke();
  }
}
function drawAll() {
  if (page === 0) {
    graph("g_head", [[hist.head, "#4c8dff"]], 0, 120, N, [[30, "afraid 30"], [10, "jolt 10"]]);
    graph("g_base", [[hist.base, "#4c8dff"]], 0, 120, N, [[20, "object 20"]]);
  } else {
    C.hormones.forEach(([, , col], i) => graph(`g_h${i}`, [[hist.h[i], col]], 0, 1, N, [], false));
    graph("g_cpg", [[hist.o1, "#4c8dff"], [hist.o2, "#ff9f0a"]], -1, 1, 200, []);
  }
}

// ---------- state ----------
function put(id, txt, col) { const e = $(id); if (e.textContent !== txt) e.textContent = txt; if (col) e.style.color = col; }
async function poll() {
  let s;
  try { s = await (await fetch(`/state?pin=${PIN}&d=${dSeq}&l=${lSeq}`)).json(); }
  catch (e) { put("ctxt", "laptop not reachable"); $("cdot").style.background = "#ff453a"; return; }
  S = s;
  $("cdot").style.background = s.link ? "#34c759" : (s.connected ? "#ff453a" : "#8b919c");
  put("ctxt", s.connected ? (s.link ? "ESP32" : "ESP32 silent") : "TEST MODE (no ESP32)");
  const col = C.emo[s.emotion] || "#8b919c";
  $("bdot").style.background = col;
  put("btxt", (s.emotion ? s.emotion.toUpperCase() : "-") + (s.forced ? "  FORCED" : "") + (s.auto === false ? "  · WAITING" : ""));
  $("emo").querySelectorAll("button").forEach(b => {
    const sel = (b.dataset.e || null) === (s.forced || null);
    b.style.background = b.dataset.col ? (sel ? b.dataset.col : b.dataset.col + "38") : (sel ? "#4c8dff" : "");
    b.style.color = !sel ? "" : (b.dataset.col ? (["normal", "excited", "happy", "interested"].includes(b.dataset.e) ? "#000" : "#fff") : "#fff");
  });
  if (s.cond !== null) mark($("cond"), "c", s.cond);
  if (s.auto !== null) mark($("auto"), "a", s.auto ? 1 : 0);
  put("trial", s.trial_s === null || s.trial_s < 0 ? "--:--" :
      `${String(Math.floor(s.trial_s / 60)).padStart(2, "0")}:${String(Math.floor(s.trial_s % 60)).padStart(2, "0")}`);
  // new D rows -> graphs
  if (s.seq < dSeq) { dSeq = 0; }
  for (const [seq, v] of s.rows) {
    if (seq <= dSeq) continue; dSeq = seq;
    push(hist.base, v[0], N); push(hist.head, v[1], N);
    for (let i = 0; i < 5; i++) push(hist.h[i], v[2 + i], N);
    push(hist.o1, v[7], 200); push(hist.o2, v[8], 200);
  }
  if (s.rows.length) drawAll();
  // monitor numbers
  for (const k of ["head", "base"]) {
    const [f, r] = s.tof[k];
    put(`t_${k}`, f === null ? (s.link ? "invalid" : "-") : `${f.toFixed(1)} cm`, f === null ? "#8b919c" : "#e8eaed");
    put(`t_${k}_raw`, f === null || r === null ? "" : `raw ${r.toFixed(1)}`);
  }
  const cm = s.cam;
  put("s_obj", cm.obj ? `${cm.obj} · ${cm.obj_id}` : "-");
  put("s_person", cm.person ? "Yes" : "No", cm.person ? "#34c759" : "#8b919c");
  put("s_wave", cm.waving ? "Waving!" : `${cm.waves} times`, cm.waving ? "#f5b942" : "#e8eaed");
  put("s_fps", cm.fps.toFixed(1));
  // control numbers
  C.hormones.forEach(([n], i) => { const a = hist.h[i]; const v = a.length ? a[a.length - 1] : null; put(`h${i}`, v === null ? "-" : v.toFixed(2)); });
  for (const [j, t] of Object.entries(s.temps)) {
    const txt = t === null ? "-" : `${t.toFixed(0)} °C`;
    if ($(`temp_${j}`)) put(`temp_${j}`, txt, t === null ? "#8b919c" : (t >= 58 ? "#ff453a" : (t >= 50 ? "#f5b942" : "#8b919c")));
    if ($(`mtemp_${j}`)) put(`mtemp_${j}`, txt, t === null ? "#8b919c" : (t >= 58 ? "#ff453a" : (t >= 50 ? "#f5b942" : "#e8eaed")));   // Monitor page
  }
  put("nap", s.napping ? "Resting - cooling motors" : "");
  put("mnap", s.napping ? "Resting - cooling motors" : "");
  put("saved", s.saved === null ? "" : (s.saved ? "● saved on ESP32" : "● not saved yet"), s.saved ? "#34c759" : "#8b919c");
  for (const [key, st] of Object.entries(rows)) {
    const v = key in s.values ? s.values[key] : null;
    if (v === st.now) continue;
    st.now = v; st.nowEl.textContent = v === null ? "-" : fmt(st.def, v) + (st.def.unit ? " " + st.def.unit : "");
    if (!st.pending && document.activeElement !== st.input && v !== null) st.input.value = fmt(st.def, v);
  }
  // log
  if (s.log.length) {
    const box = $("log"), atEnd = box.scrollTop + box.clientHeight >= box.scrollHeight - 4;
    for (const [n, t] of s.log) { if (n <= lSeq) continue; lSeq = n; box.insertAdjacentHTML("beforeend", esc(t) + "\n"); }
    while (box.childNodes.length > 400) box.removeChild(box.firstChild);
    if (atEnd) box.scrollTop = box.scrollHeight;
  }
  if (s.log_seq < lSeq) lSeq = 0;
}

// ---------- camera picture: only while Monitor is visible, next one only after the last arrived ----------
const img = $("camimg"); let camBusy = false;
function camTick() {
  if (page !== 0 || document.hidden || camBusy || !(S && S.cam.ok)) return;
  camBusy = true; img.src = `/cam.jpg?pin=${PIN}&t=${Date.now()}`;
}
img.onload = img.onerror = () => { camBusy = false; };

build();
let polling = false;
setInterval(async () => { if (document.hidden || polling) return; polling = true; try { await poll(); } finally { polling = false; } }, 200);
setInterval(camTick, 140);
window.addEventListener("resize", drawAll);
</script></body></html>
"""
