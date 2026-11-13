"""หน้าจอ OpenCV: กล้อง + กรอบตรวจจับ | โคมจำลอง + ไฟ | แถบฮอร์โมน (ตัวอักษรเป็นอังกฤษเพราะ cv2.putText ไม่รองรับภาษาไทย)"""
import math

import cv2
import numpy as np

from lamp import forward_kinematics, LIMITS

W, H = 1200, 640
CAM_W, CAM_H = 640, 480
PANEL_X = 660
STATE_COLOR = {   # BGR
    "Idle": (200, 170, 120), "Curious": (60, 200, 240), "Engage": (110, 210, 110),
    "Fear": (200, 110, 190), "Sleep": (150, 90, 60), "Blind": (40, 150, 255),
}
HORMONE_COLOR = {"caution": (90, 90, 240), "curiosity": (60, 200, 240),
                 "affinity": (130, 210, 120), "sleepiness": (200, 130, 90)}

_TH = math.radians(-25.0)
_R = (math.cos(_TH), math.sin(_TH))
_F = (-math.sin(_TH), math.cos(_TH))
_E = math.radians(18.0)
_SCALE = 235.0


def _proj(P, ox, oy):
    X, Y, Z = P
    sx = X * _R[0] + Y * _R[1]
    depth = X * _F[0] + Y * _F[1]
    up = Z * math.cos(_E) + depth * math.sin(_E)
    return int(ox + _SCALE * sx), int(oy - _SCALE * up)


def _text(img, s, org, scale=0.5, color=(230, 230, 230), thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw_lamp(canvas, lamp, x0, y0, w, h):
    panel = canvas[y0:y0 + h, x0:x0 + w]
    panel[:] = (28, 28, 32)
    ox, oy = w // 2 - 90, h - 50
    pts = forward_kinematics(lamp.angles)
    P = {k: _proj(v, ox, oy) for k, v in pts.items() if k != "gaze_elev"}
    # พื้นและเงา
    cv2.ellipse(panel, (ox, oy + 6), (150, 26), 0, 0, 360, (40, 40, 46), -1)
    hx, hy, _ = pts["head"]
    sh = _proj((hx, hy, 0.0), ox, oy)
    cv2.ellipse(panel, (sh[0], sh[1] + 6), (34, 8), 0, 0, 360, (22, 22, 26), -1)

    rgb = lamp.light["rgb"]
    inten = lamp.light["intensity"]
    col = (rgb[2], rgb[1], rgb[0])                                  # RGB -> BGR
    # ลำแสง
    ax = tuple(a - b for a, b in zip(pts["tip"], pts["head"]))
    n = math.sqrt(sum(a * a for a in ax)) or 1.0
    ax = tuple(a / n for a in ax)
    far_a = tuple(p + 1.1 * a for p, a in zip(pts["rim_a"], ax))
    far_b = tuple(p + 1.1 * a for p, a in zip(pts["rim_b"], ax))
    beam = np.array([P["rim_a"], P["rim_b"], _proj(far_b, ox, oy), _proj(far_a, ox, oy)], np.int32)
    overlay = panel.copy()
    cv2.fillPoly(overlay, [beam], col)
    cv2.addWeighted(overlay, 0.30 * inten, panel, 1 - 0.30 * inten, 0, panel)

    # โครง
    cv2.line(panel, P["base"], P["shoulder"], (110, 110, 118), 8, cv2.LINE_AA)
    cv2.line(panel, P["shoulder"], P["elbow"], (150, 150, 160), 7, cv2.LINE_AA)
    cv2.line(panel, P["elbow"], P["head"], (150, 150, 160), 7, cv2.LINE_AA)
    cv2.ellipse(panel, P["base"], (40, 9), 0, 0, 360, (95, 95, 105), -1)
    for k in ("shoulder", "elbow", "head"):
        cv2.circle(panel, P[k], 7, (200, 200, 210), -1, cv2.LINE_AA)
    shade = np.array([P["head"], P["rim_a"], P["rim_b"]], np.int32)
    cv2.fillPoly(panel, [shade], (70, 70, 80))
    cv2.polylines(panel, [shade], True, (190, 190, 200), 2, cv2.LINE_AA)
    glow_r = int(7 + 9 * inten)
    ov2 = panel.copy()
    cv2.circle(ov2, P["bulb"], glow_r + 8, col, -1, cv2.LINE_AA)
    cv2.addWeighted(ov2, 0.25 * inten, panel, 1 - 0.25 * inten, 0, panel)
    cv2.circle(panel, P["bulb"], max(4, glow_r // 2), col, -1, cv2.LINE_AA)

    # มุมมองจากด้านบน: ทิศของโคมกับทิศของคน
    cx, cy, r = w - 62, 62, 44
    cv2.circle(panel, (cx, cy), r, (50, 50, 56), 1, cv2.LINE_AA)
    _text(panel, "top view", (cx - 28, cy + r + 14), 0.38, (150, 150, 150))
    yaw = math.radians(lamp.angles["yaw"])
    cv2.line(panel, (cx, cy), (int(cx - r * math.sin(yaw)), int(cy - r * math.cos(yaw))), (230, 230, 230), 2, cv2.LINE_AA)
    return panel


def draw_camera(canvas, frame, info, snap):
    cam = canvas[10:10 + CAM_H, 10:10 + CAM_W]
    if frame is None:
        cam[:] = (30, 30, 30)
        _text(cam, "NO CAMERA SIGNAL", (200, 240), 0.8, (60, 150, 255), 2)
        return
    cam[:] = cv2.resize(frame, (CAM_W, CAM_H))
    p = snap.get("percept") if snap else None
    if info is not None:
        for d in info.detections:
            x0, y0 = int((d.cx - d.h * (0.4 if d.kind == "face" else 0.18) * CAM_H / CAM_W) * CAM_W), int((d.cy - d.h / 2) * CAM_H)
            x1, y1 = int((d.cx + d.h * (0.4 if d.kind == "face" else 0.18) * CAM_H / CAM_W) * CAM_W), int((d.cy + d.h / 2) * CAM_H)
            c = (90, 230, 90) if d.kind == "face" else (60, 160, 255)
            cv2.rectangle(cam, (x0, y0), (x1, y1), c, 2)
            _text(cam, d.kind, (x0, max(14, y0 - 6)), 0.5, c)
    if p is not None and p.present:
        tx, ty = int(p.cx * CAM_W), int(p.cy * CAM_H)
        cv2.drawMarker(cam, (tx, ty), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)
    cv2.line(cam, (CAM_W // 2 - 8, CAM_H // 2), (CAM_W // 2 + 8, CAM_H // 2), (120, 120, 120), 1)
    cv2.line(cam, (CAM_W // 2, CAM_H // 2 - 8), (CAM_W // 2, CAM_H // 2 + 8), (120, 120, 120), 1)


def draw_hud(canvas, snap, x0, y0, w):
    if not snap:
        return
    H_, S_, E_ = snap["H"], snap["S"], snap["E"]
    y = y0
    _text(canvas, "hormone level (bar)   stimulus now (tick)   receptor effect", (x0, y), 0.45, (170, 170, 170))
    y += 14
    for name in ("caution", "curiosity", "affinity", "sleepiness"):
        bx, bw, bh = x0 + 100, w - 250, 20
        _text(canvas, name, (x0, y + 15), 0.5, HORMONE_COLOR[name])
        cv2.rectangle(canvas, (bx, y), (bx + bw, y + bh), (60, 60, 66), 1)
        cv2.rectangle(canvas, (bx, y), (bx + int(bw * H_[name]), y + bh), HORMONE_COLOR[name], -1)
        s = S_.get(name)
        if s is None:
            _text(canvas, "?", (bx + bw + 6, y + 15), 0.5, (60, 150, 255))
        else:
            tx = bx + int(bw * s)
            cv2.line(canvas, (tx, y - 3), (tx, y + bh + 3), (255, 255, 255), 2)
        _text(canvas, f"H={H_[name]:.2f}  e={E_[name]:.2f}", (bx + bw + 28, y + 15), 0.42, (190, 190, 190))
        y += 30
    return y


def render(frame, info, snap, lamp, fps, extra=None):
    canvas = np.full((H, W, 3), 18, np.uint8)
    draw_camera(canvas, frame, info, snap)
    state = snap["state"] if snap else "Idle"
    sc = STATE_COLOR.get(state, (200, 200, 200))
    cv2.rectangle(canvas, (PANEL_X, 10), (W - 10, 340), (28, 28, 32), -1)
    draw_lamp(canvas, lamp, PANEL_X, 10, W - 10 - PANEL_X, 330)
    cv2.rectangle(canvas, (PANEL_X + 10, 18), (PANEL_X + 190, 52), sc, -1)
    _text(canvas, state.upper(), (PANEL_X + 20, 42), 0.9, (20, 20, 20), 2)
    if lamp.stale:
        _text(canvas, "PACKET STALE -> SAFE", (PANEL_X + 200, 42), 0.55, (60, 150, 255), 2)

    y = draw_hud(canvas, snap, PANEL_X + 10, 362, W - PANEL_X - 20) or 362
    if snap:
        p = snap["percept"]
        pr = snap["params"]
        lines = [
            f"zone={p.zone:5s} p={p.p:4.2f} closing={p.closing:+.2f} dwell={p.dwell:4.1f}s motion={p.motion:.2f}"
            + ("  RUSHING" if p.rushing else ""),
            f"facing={int(p.facing)} crowd={int(p.crowd)} novelty={p.novelty:.2f} quiet={p.quiet_time:4.1f}s "
            f"light={p.light:.2f}" + ("" if p.valid else "   CAMERA INVALID"),
            "params " + " ".join(f"{k}={pr[k]:.2f}" for k in ("tempo", "amp", "lean")),
            "       " + " ".join(f"{k}={pr[k]:.2f}" for k in ("gaze_follow", "brightness", "warmth")),
        ]
        for ln in lines:
            _text(canvas, ln, (PANEL_X + 10, y + 8), 0.42, (200, 200, 200))
            y += 18
        for t, msg in snap.get("alerts", [])[-2:]:
            _text(canvas, f"ALERT {msg}", (PANEL_X + 10, y + 8), 0.45, (60, 150, 255))
            y += 18
    ang = lamp.angles
    _text(canvas, "joints " + " ".join(f"{k}={v:6.1f}" for k, v in ang.items()), (10, CAM_H + 32), 0.45, (200, 200, 200))
    _text(canvas, f"fps={fps:4.1f}   keys: q quit | r reset hormones | b fake camera fault | s save png"
          + (f" | {extra}" if extra else ""), (10, CAM_H + 54), 0.45, (150, 150, 150))
    return canvas
