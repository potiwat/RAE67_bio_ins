"""ไดรเวอร์บัส Feetech SCS (SCS15) แบบ half-duplex สำหรับ MicroPython/ESP32

รูปแบบแพ็กเก็ต (ตรวจกับ SDK ของ Feetech แล้ว)
    FF FF  ID  LEN  INST  PARAM...  CHK        โดย CHK = (~sum(ID..PARAM)) & 0xFF
    LEN = จำนวนไบต์หลัง LEN ทั้งหมด (INST + PARAM + CHK)

เรื่องที่พลาดกันบ่อย
  - SCS/SCSCL เก็บเลข 16 บิตแบบ big-endian ส่วน STS/SMS เป็น little-endian
    ถ้าอ่านมุมแล้วค่ากระโดดแปลกๆ ให้สลับ SCS_BIG_ENDIAN ใน config.py (tools/scan.py ช่วยเช็คได้)
  - โหลดและความเร็วเป็น sign-magnitude: บิต 10 คือเครื่องหมาย ไม่ใช่ two's complement
  - half-duplex: ต้องรอให้ส่งจบจริงก่อนสลับขาทิศเป็นรับ ไม่งั้นจะกินคำตอบของตัวเอง
"""
try:
    from utime import ticks_ms, ticks_diff, sleep_us
except ImportError:                      # CPython (ไว้รันชุดทดสอบบนคอม)
    import time as _t

    def ticks_ms():
        return int(_t.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

    def sleep_us(us):
        _t.sleep(us / 1000000.0)

BROADCAST_ID = 0xFE
INST_PING = 1
INST_READ = 2
INST_WRITE = 3
INST_SYNC_WRITE = 0x83

# ---- memory table ของ SCS15 (ยืนยันด้วย tools/scan.py ก่อนเชื่อ) ----
ADDR_MIN_ANGLE = 9
ADDR_MAX_ANGLE = 11
ADDR_MAX_TORQUE = 16        # EEPROM
ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_GOAL_TIME = 44
ADDR_GOAL_SPEED = 46
ADDR_PRESENT_POSITION = 56
ADDR_PRESENT_SPEED = 58
ADDR_PRESENT_LOAD = 60
ADDR_PRESENT_VOLTAGE = 62
ADDR_PRESENT_TEMPERATURE = 63

ERR_VOLTAGE, ERR_ANGLE, ERR_OVERHEAT, ERR_OVERELE, ERR_OVERLOAD = 1, 2, 4, 8, 32


def _sign_mag(v, bit=10):
    """แปลง sign-magnitude ของ Feetech เป็นจำนวนเต็มมีเครื่องหมาย"""
    return -(v & ~(1 << bit)) if (v & (1 << bit)) else v


class SCSBus:
    """uart = อ็อบเจกต์ที่มี read/write/any ; dir_pin = อ็อบเจกต์ที่มี value() (None = โหมด echo)"""

    def __init__(self, uart, dir_pin=None, big_endian=True, baud=1000000, timeout_ms=6):
        self.uart, self.dir_pin, self.big_endian = uart, dir_pin, big_endian
        self.timeout_ms = timeout_ms
        self.byte_us = max(1, int(10 * 1000000 / baud))
        self.errors = 0          # นับแพ็กเก็ตที่อ่านไม่สำเร็จ (ไว้ดูสุขภาพสาย)
        self.ok = 0

    # ------------------------------------------------------------ ระดับไบต์
    def _word(self, lo_first_pair):
        a, b = lo_first_pair
        return ((a << 8) | b) if self.big_endian else ((b << 8) | a)

    def _split(self, value):
        value &= 0xFFFF
        hi, lo = (value >> 8) & 0xFF, value & 0xFF
        return (hi, lo) if self.big_endian else (lo, hi)

    def _tx(self, body):
        """body = [id, len, inst, params...] ; เติม header + checksum แล้วส่ง"""
        chk = (~sum(body)) & 0xFF
        pkt = bytes([0xFF, 0xFF] + body + [chk])
        if self.dir_pin is not None:
            self.dir_pin.value(1)                       # ส่ง
        while self.uart.any():                          # ทิ้งขยะค้างท่อ
            self.uart.read()
        self.uart.write(pkt)
        try:
            self.uart.flush()                           # รอให้ shift register ว่างจริง
        except (AttributeError, NotImplementedError):
            sleep_us(len(pkt) * self.byte_us + 60)
        if self.dir_pin is not None:
            self.dir_pin.value(0)                       # รับ
        elif True:
            self._drain_echo(len(pkt))
        return pkt

    def _drain_echo(self, n):
        """โหมด echo: ไบต์ที่เราส่งจะวนกลับเข้ามาเอง ต้องทิ้งก่อน"""
        got, t0 = 0, ticks_ms()
        while got < n and ticks_diff(ticks_ms(), t0) < self.timeout_ms:
            d = self.uart.read(n - got)
            if d:
                got += len(d)

    def _rx(self, want_params, expect_id=None):
        """อ่าน status packet ; คืน (params, error) หรือ (None, None) ถ้าไม่สำเร็จ

        ต้องเช็คว่า ID ในคำตอบตรงกับตัวที่ถาม ไม่งั้นคำตอบที่ค้างในบัฟเฟอร์จากตัวก่อนหน้า
        จะถูกนับเป็นคำตอบของตัวนี้ -> สแกนเจอ ID ผีที่ไม่มีอยู่จริง
        ถ้าเจอแพ็กเก็ตที่ไม่ใช่ของเรา ให้ข้ามแล้วอ่านต่อจนหมดเวลา
        """
        need = 6 + want_params
        buf = b""
        t0 = ticks_ms()
        while ticks_diff(ticks_ms(), t0) < self.timeout_ms:
            d = self.uart.read(need)
            if d:
                buf += d
            pos = 0
            while True:
                i = buf.find(b"\xff\xff", pos)
                if i < 0 or len(buf) - i < need:
                    break
                p = buf[i:i + need]
                if ((~sum(p[2:-1])) & 0xFF) == p[-1] and (expect_id is None or p[2] == expect_id):
                    self.ok += 1
                    return p[5:5 + want_params], p[4]
                pos = i + 2                    # ไม่ใช่ของเรา -> หา header ถัดไป
            if len(buf) > 4 * need:            # กันบัฟเฟอร์บวมตอนสายรบกวนหนัก
                buf = buf[-2 * need:]
        self.errors += 1
        return None, None

    # ------------------------------------------------------------ คำสั่งพื้นฐาน
    def ping(self, sid):
        self._tx([sid, 2, INST_PING])
        params, err = self._rx(0, expect_id=sid)
        return None if params is None else err

    def read(self, sid, addr, n):
        self._tx([sid, 4, INST_READ, addr, n])
        params, err = self._rx(n, expect_id=sid)
        return params

    def write(self, sid, addr, data):
        data = list(data)
        self._tx([sid, 3 + len(data), INST_WRITE, addr] + data)
        if sid != BROADCAST_ID:
            self._rx(0, expect_id=sid)
        return True

    def read_word(self, sid, addr):
        d = self.read(sid, addr, 2)
        return None if d is None else self._word((d[0], d[1]))

    def write_word(self, sid, addr, value):
        return self.write(sid, addr, self._split(value))

    def sync_write_positions(self, items, speed=0):
        """items = [(id, tick)] / [(id, tick, speed)] / [(id, tick, speed, time_ms)]
        -> สั่งทุกตัวในแพ็กเก็ตเดียว (ไม่มีคำตอบกลับ) ; เขียน goal position + goal time + goal speed (addr 42..47)
        goal speed คือเพดานความเร็วฝั่งเซอร์โว เป็นชั้นกันซ้ำของ slew-rate ในซอฟต์แวร์"""
        per = 7                                          # addr ของตัวเอง + 6 ไบต์ข้อมูล
        body = [BROADCAST_ID, (per * len(items)) + 4, INST_SYNC_WRITE, ADDR_GOAL_POSITION, 6]
        for it in items:
            sid, tick = it[0], it[1]
            sp = self._split(it[2] if len(it) > 2 else speed)
            ph, pl = self._split(int(tick))
            tm = self._split(int(it[3]) if len(it) > 3 else 0)
            body += [sid, ph, pl, tm[0], tm[1], sp[0], sp[1]]
        self._tx(body)

    # ------------------------------------------------------------ ระดับสูง
    def torque(self, sid, on):
        return self.write(sid, ADDR_TORQUE_ENABLE, [1 if on else 0])

    def feedback(self, sid):
        """อ่าน position/speed/load/voltage/temp ในครั้งเดียว (addr 56..63)
        คืน dict หรือ None ถ้าอ่านไม่สำเร็จ"""
        d = self.read(sid, ADDR_PRESENT_POSITION, 8)
        if d is None or len(d) < 8:
            return None
        return {
            "tick": self._word((d[0], d[1])),
            "speed": _sign_mag(self._word((d[2], d[3]))),
            "load": _sign_mag(self._word((d[4], d[5]))),
            "volt": d[6] / 10.0,
            "temp": d[7],
        }
