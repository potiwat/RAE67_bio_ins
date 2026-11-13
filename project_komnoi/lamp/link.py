"""โปรโตคอลระหว่างโน้ตบุ๊กกับ ESP32 (ใช้ได้ทั้งสองฝั่ง: โค้ดเดียวกัน)

เฟรม:  AA 55 | len(1) | payload | crc16(2, little endian)
  ลงมา (คำสั่ง, 22 ไบต์): seq u16 | t_ms u32 | mode u8 | flags u8 |
                          tempo amp lean gaze_follow brightness warmth : int16 x1000 ... 
     -> ใช้ 6 พารามิเตอร์ x int16 (คูณ 1000) + gaze yaw/pitch int16 (คูณ 10)
  ขึ้นไป (telemetry): seq u16 | t_ms u32 | state u8 | fault u16 |
                      5 x (pos int16 x10, load int16, temp u8)

ทุกเฟรมมี seq และ t_ms เพื่อให้ทั้งสองฝั่งทิ้งข้อมูลเก่าได้ (กัน race condition)
"""
import struct

HDR = b"\xaa\x55"
PARAM_NAMES = ("tempo", "amp", "lean", "gaze_follow", "brightness", "warmth")
MODES = ("Idle", "Curious", "Engage", "Fear", "Sleep", "Blind", "Protect", "Peek", "Sick")   # Peek = หลับแล้วเงยหัวแอบดู
MODE_ID = {}
for _i, _m in enumerate(MODES):
    MODE_ID[_m] = _i

FLAG_GAZE = 1
# ห้ามใช้ตัวเลขนำหน้าในรูปแบบ (เช่น "8h") เพราะ struct ของ MicroPython ไม่รองรับ
# ต้องเขียนตัวอักษรซ้ำเอา ไม่งั้น unpack จะพังเงียบๆ บนบอร์ด
CMD_FMT = "<HIBB" + "h" * 8    # seq, t_ms, mode, flags, 6 params, gaze yaw, gaze pitch
CMD_TAIL = "<" + "h" * 8
TLM_FMT = "<HIBH" + "hhB" * 5 + "HBBB"   # + เซนเซอร์: dist_mm, wet_pct, key, key_seq
TLM_SENSORS = "<HBBB"
NO_SENSORS = (0xFFFF, 255, 0, 0)


def crc16(data):
    """CCITT-FALSE ; เล็กและพอสำหรับสาย USB สั้นๆ"""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else ((crc << 1) & 0xFFFF)
    return crc


def frame(payload):
    return HDR + bytes([len(payload)]) + payload + struct.pack("<H", crc16(payload))


def encode_command(seq, t_ms, mode, params, gaze=None):
    flags = FLAG_GAZE if gaze is not None else 0
    gy, gp = (int(gaze[0] * 10), int(gaze[1] * 10)) if gaze is not None else (0, 0)
    vals = [int(round(params[n] * 1000)) for n in PARAM_NAMES]
    body = struct.pack(CMD_FMT, seq & 0xFFFF, t_ms & 0xFFFFFFFF,
                       MODE_ID.get(mode, 5), flags, *(vals + [gy, gp]))
    return frame(body)


def decode_command(body):
    seq, t_ms, mode, flags = struct.unpack("<HIBB", body[:8])
    rest = struct.unpack(CMD_TAIL, body[8:24])
    params = {}
    for i, n in enumerate(PARAM_NAMES):
        params[n] = rest[i] / 1000.0
    gaze = (rest[6] / 10.0, rest[7] / 10.0) if (flags & FLAG_GAZE) else None
    return {"seq": seq, "t_ms": t_ms,
            "mode": MODES[mode] if mode < len(MODES) else "Blind",
            "params": params, "gaze": gaze}


def encode_telemetry(seq, t_ms, state, fault, joints, sensors=None):
    """joints = [(pos_deg, load, temp)] x 5 ; sensors = (dist_mm, wet_pct, key_code, key_seq)
    dist_mm 0xFFFF / wet_pct 255 = ไม่รู้ ; key_code 0 = ยังไม่เคยกด"""
    flat = []
    for pos, load, temp in joints:
        flat += [int(round(pos * 10)), int(load), int(temp) & 0xFF]
    return frame(struct.pack(TLM_FMT, seq & 0xFFFF, t_ms & 0xFFFFFFFF,
                             MODE_ID.get(state, 5), fault & 0xFFFF,
                             *(flat + list(sensors or NO_SENSORS))))


def decode_telemetry(body):
    seq, t_ms, state, fault = struct.unpack("<HIBH", body[:9])
    rest = struct.unpack("<" + "hhB" * 5, body[9:34])
    joints = []
    for i in range(5):
        joints.append((rest[i * 3] / 10.0, rest[i * 3 + 1], rest[i * 3 + 2]))
    out = {"seq": seq, "t_ms": t_ms,
           "state": MODES[state] if state < len(MODES) else "Blind",
           "fault": fault, "joints": joints}
    out.update(_decode_sensors(body[34:]))      # ไม่ใช้ {**x} เพราะ MicroPython บางรุ่นไม่รองรับ
    return out


def _decode_sensors(tail):
    """รองรับเฟรมรุ่นเก่าที่ไม่มีเซนเซอร์ (คืนค่า "ไม่รู้")"""
    if len(tail) < 5:
        d, w, k, ks = NO_SENSORS
    else:
        d, w, k, ks = struct.unpack(TLM_SENSORS, tail[:5])
    return {"dist_m": None if d == 0xFFFF else d / 1000.0,
            "wet": None if w == 255 else w / 100.0,
            "key": chr(k) if k else None, "key_seq": ks}


class Reader:
    """ป้อนไบต์เข้ามาเรื่อยๆ แล้วดึงเฟรมที่สมบูรณ์ออกไป (ทนต่อไบต์ขยะและเฟรมขาด)

    ใช้ bytes ไม่ใช่ bytearray เพราะ MicroPython ลบช่วงของ bytearray ไม่ได้
    (del buf[:n] -> TypeError: 'bytearray' object doesn't support item deletion)
    """

    def __init__(self, max_len=64):
        self.buf = b""
        self.max_len = max_len
        self.bad = 0

    def feed(self, data):
        if data:
            self.buf += bytes(data)
            cap = 8 * (self.max_len + 5)
            if len(self.buf) > cap:
                self.buf = self.buf[-4 * (self.max_len + 5):]
        out = []
        while True:
            i = self.buf.find(HDR)
            if i < 0:
                self.buf = self.buf[-1:] if self.buf else b""
                break
            if i:
                self.buf = self.buf[i:]
            if len(self.buf) < 3:
                break
            ln = self.buf[2]
            if ln > self.max_len:
                self.bad += 1
                self.buf = self.buf[2:]
                continue
            total = 3 + ln + 2
            if len(self.buf) < total:
                break
            body = self.buf[3:3 + ln]
            crc = self.buf[3 + ln] | (self.buf[4 + ln] << 8)
            if crc == crc16(body):
                self.buf = self.buf[total:]
                out.append(body)
            else:
                self.bad += 1
                self.buf = self.buf[2:]       # header ปลอม: ถอยไปหา header ตัวถัดไป
        return out
