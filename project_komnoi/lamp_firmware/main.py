"""ไฟล์ที่ ESP32 รันตอนบูต -- วางไว้ที่ /main.py บนบอร์ด

ก่อนใช้งานจริงต้องทำตามลำดับนี้
  1. tools/scan.py       เช็คว่าเจอเซอร์โวครบ 5 ตัว, endianness ถูก, memory table ตรง
  2. tools/calibrate.py  หา center_tick, invert, soft limit ของแต่ละข้อต่อ -> เอาไปแก้ config.py
  3. main.py             ใช้งานจริง (ตอนแรกให้ยกโคมลอยไว้ ยังไม่ต้องมีคนใกล้)
"""
import gc

from machine import UART, Pin, PWM
import os as _os
import sys
import time

import config as cfg
import robot as robot_mod
from scs import SCSBus
from led import Light


def build():
    try:                                         # MicroPython บน ESP32 เริ่มที่ 160 MHz -> เร่งเป็น 240 (เร็วขึ้น ~1.5 เท่า)
        import machine
        machine.freq(getattr(cfg, "CPU_HZ", 240000000))
    except Exception:
        pass
    dir_pin = Pin(cfg.PIN_DIR, Pin.OUT, value=0) if cfg.PIN_DIR is not None else None
    uart = UART(cfg.UART_ID, baudrate=cfg.BAUD, tx=cfg.PIN_TX, rx=cfg.PIN_RX, timeout=5)
    bus = SCSBus(uart, dir_pin=dir_pin, big_endian=cfg.SCS_BIG_ENDIAN, baud=cfg.BAUD)
    light = None
    if cfg.PIN_LED is not None:
        try:
            led_max = getattr(cfg, "LED_MAX", 0.95)
            if getattr(cfg, "LED_TYPE", "pwm") == "neopixel":
                from neopixel import NeoPixel
                n = getattr(cfg, "LED_COUNT", 16)
                np = NeoPixel(Pin(cfg.PIN_LED, Pin.OUT), n)
                np.fill((0, 0, 0))
                np.write()
                light = Light(neopixel=np, n=n, max_b=led_max)
            else:
                light = Light(pwm=PWM(Pin(cfg.PIN_LED), freq=1000), max_b=led_max)
        except Exception as e:
            print("ไฟใช้ไม่ได้:", e)
    estop = Pin(cfg.PIN_ESTOP, Pin.IN, Pin.PULL_UP) if cfg.PIN_ESTOP is not None else None

    return bus, light, estop


class StdioLink:
    """ลิงก์กับโน้ตบุ๊กผ่าน stdin/stdout ของ REPL (สาย USB เส้นเดียวกับที่ใช้ flash)

    ทำไมไม่ใช้ UART(0) ตรงๆ: UART0 เป็นพอร์ตของ REPL
      - ตั้ง rxbuf/txbuf ไม่ได้ -> ValueError: REPL UART buffer size is fixed
      - ถึงเปิดได้ REPL ก็ยังแย่งอ่านไบต์
    ตอนสคริปต์กำลังรัน สคริปต์เป็นเจ้าของ stdin อยู่แล้ว จึงอ่านตรงนี้ได้เลย
    ต้องปิด Ctrl-C ด้วย ไม่งั้นไบต์ 0x03 ที่บังเอิญอยู่ในเฟรมจะทำให้โปรแกรมหยุดกลางคัน
    """

    def __init__(self):
        import select
        import micropython
        self._poll = select.poll()
        self._poll.register(sys.stdin, select.POLLIN)
        micropython.kbd_intr(-1)
        self._kbd_off = True
        self.read_errors = 0
        self.rx_bytes = 0

    def any(self):
        return 1 if self._poll.poll(0) else 0

    def read(self, limit=256):
        out = bytearray()
        try:
            while len(out) < limit and self._poll.poll(0):
                b = sys.stdin.buffer.read(1)
                if not b:
                    break
                out += b
        except Exception as e:
            self.read_errors += 1
            if self.read_errors <= 3:
                _log_exc("อ่าน stdin ไม่ได้", e)
        self.rx_bytes += len(out)
        return bytes(out) if out else None

    def write(self, data):
        try:
            sys.stdout.buffer.write(data)
        except Exception:
            pass

    def close(self):
        if self._kbd_off:
            try:
                import micropython
                micropython.kbd_intr(3)        # เปิด Ctrl-C กลับ
            except Exception:
                pass
            self._kbd_off = False


class WifiLink:
    """ลิงก์ผ่าน WiFi UDP -- REPL ว่างตลอด จึงอัปโหลดและ Ctrl-C ได้ตามปกติ

    โหมด AP: บอร์ดปล่อย WiFi ของตัวเอง โน้ตบุ๊กต่อเข้ามาแล้วยิง UDP ไปที่ 192.168.4.1
    บอร์ดจำที่อยู่ของโน้ตบุ๊กจากแพ็กเก็ตแรกที่ได้รับ แล้วส่ง telemetry กลับไปที่นั่น
    """

    def __init__(self):
        import network
        import socket
        self._socket = socket
        if cfg.LINK_MODE == "wifi_sta":
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            if not wlan.isconnected():
                wlan.connect(cfg.STA_SSID, cfg.STA_PASSWORD)
                for _ in range(100):
                    if wlan.isconnected():
                        break
                    time.sleep(0.1)
            self.ip = wlan.ifconfig()[0] if wlan.isconnected() else None
            print("WiFi STA:", self.ip or "ต่อไม่ได้")
        else:
            ap = network.WLAN(network.AP_IF)
            ap.active(True)
            try:
                ap.config(essid=cfg.LINK_SSID, password=cfg.LINK_PASSWORD, authmode=3)
            except Exception:
                ap.config(essid=cfg.LINK_SSID)
            self.ip = ap.ifconfig()[0]
            print("WiFi AP: ต่อเข้า '%s' รหัส '%s' แล้วยิงไปที่ %s:%d"
                  % (cfg.LINK_SSID, cfg.LINK_PASSWORD, self.ip, cfg.LINK_PORT))

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", cfg.LINK_PORT))
        self.sock.setblocking(False)
        self.peer = None
        self.rx_bytes = 0
        self.read_errors = 0

    def any(self):
        return 1

    def read(self, limit=512):
        out = bytearray()
        for _ in range(8):                       # ดึงได้หลายแพ็กเก็ตต่อรอบ ไม่ให้คิวบวม
            try:
                data, addr = self.sock.recvfrom(limit)
            except Exception:
                break
            if not data:
                break
            self.peer = addr
            out += data
        self.rx_bytes += len(out)
        return bytes(out) if out else None

    def write(self, data):
        if self.peer is None:
            return
        try:
            self.sock.sendto(data, self.peer)
        except Exception:
            pass

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def open_host_link():
    if cfg.LINK_MODE in ("wifi_ap", "wifi_sta"):
        return WifiLink()
    return StdioLink()


def _log_exc(msg, e):
    """เขียน traceback ลง lamp.log (REPL ใช้ไม่ได้ตอนลูปทำงาน)"""
    try:
        with open("lamp.log", "a") as f:
            f.write(msg + ": " + repr(e) + "\n")
            try:
                sys.print_exception(e, f)
            except Exception:
                pass
            f.write("\n")
    except Exception:
        pass


def _drain_stdin():
    """ทิ้งไบต์ค้างใน stdin ทั้งหมด (ไม่บล็อก)"""
    try:
        import select
        p = select.poll()
        p.register(sys.stdin, select.POLLIN)
        n = 0
        while p.poll(0) and n < 4096:
            sys.stdin.buffer.read(1)
            n += 1
    except Exception:
        pass


def _log(msg):
    """ตอนลูปทำงาน REPL ใช้ไม่ได้ ข้อความ debug จึงไปที่ไฟล์ แล้วพิมพ์ออกมาตอนบูตครั้งหน้า"""
    try:
        try:
            if _os.stat("lamp.log")[6] > 8000:     # ไฟล์โตเกิน -> เริ่มใหม่
                _os.remove("lamp.log")
        except OSError:
            pass
        with open("lamp.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


ABORT_WINDOW_S = 5


def _print_log():
    """พิมพ์ lamp.log ออก stdout ตอนบูต -- อ่านได้ด้วย sniff.py โดยไม่ต้องเข้า REPL"""
    try:
        with open("lamp.log") as f:
            data = f.read()
    except OSError:
        print("---- lamp.log: ไม่มีไฟล์ ----")
        return
    print("---- lamp.log (%d ไบต์) ----" % len(data))
    print(data[-2000:] if len(data) > 2000 else data)
    print("---- จบ lamp.log ----")


def run(host_link=True, abort_window=ABORT_WINDOW_S):
    """host_link=False : รันโคมอย่างเดียว ไม่ต่อกับโน้ตบุ๊ก -> REPL ยังใช้ได้ กด Ctrl-C หยุดได้
                         ใช้ตอนทดสอบการเคลื่อนไหวครั้งแรก
       host_link=True  : ต่อกับโน้ตบุ๊กจริง -> REPL ใช้ไม่ได้ ต้องกดปุ่ม EN เพื่อกลับมา

    ช่วงต้น abort_window วินาที กด Ctrl-C ได้เพื่อยกเลิก"""
    _print_log()
    if abort_window:
        print("กำลังจะเริ่มโคม (host_link=%s) -- กด Ctrl-C ภายใน %d วินาทีเพื่อยกเลิก"
              % (host_link, abort_window))
        try:
            for _ in range(abort_window):
                time.sleep(1)
        except KeyboardInterrupt:
            print("ยกเลิกแล้ว -- REPL ใช้ได้ปกติ")
            return
        _drain_stdin()        # ทิ้งไบต์ที่โน้ตบุ๊กส่งมาระหว่างรอ ไม่งั้นเฟรมครึ่งๆ จะทำให้ decode เพี้ยน
    bus, light, estop = build()
    host = open_host_link() if host_link else None
    now = time.ticks_ms() / 1000.0
    bot = robot_mod.Robot(bus, light=light, estop=estop, now=now, log=_log)
    found = bot.start(now)
    _log("boot: servo ที่ตอบ = %s" % sorted(found.keys()))
    from sensors import make_sensors
    sensors = make_sensors(cfg, log=_log)
    _log("boot: เซนเซอร์ ระยะ=%s ความชื้น=%s keypad=%s" % tuple(
        "มี" if x is not None else "-" for x in (sensors.u, sensors.m, sensors.k)))
    period_ms = int(1000.0 / cfg.FAST_HZ)
    t_prev = time.ticks_ms()
    next_ms = t_prev
    loops = overrun = ingest_err = 0
    prof = {"ingest": 0, "step": 0, "sensors": 0, "tlm": 0}   # เวลารวม (us) ต่อส่วน ไว้หาว่าลูปช้าตรงไหน
    prof_max = 0
    gc.collect()
    try:
        while True:
            now_ms = time.ticks_ms()
            dt = time.ticks_diff(now_ms, t_prev) / 1000.0
            t_prev = now_ms
            if dt <= 0 or dt > 0.25:
                dt = period_ms / 1000.0
                bot.safety.mark_resync()          # ลูปสะดุด -> ไล่จากมุมจริงใหม่
            now = now_ms / 1000.0

            t_a = time.ticks_us()
            try:
                if host is not None and host.any():
                    data = host.read()
                    if data:
                        bot.ingest(data, now)
            except Exception as e:
                ingest_err += 1
                if ingest_err <= 3:
                    _log_exc("ingest พัง", e)
            t_b = time.ticks_us()
            bot.step(dt, now)
            t_c = time.ticks_us()
            try:
                sensors.poll(now_ms)
            except Exception as e:
                _log_exc("sensors พัง", e)
            t_d = time.ticks_us()
            tlm = bot.telemetry(now, sensors.fields())
            if tlm and host is not None:
                host.write(tlm)
            t_e = time.ticks_us()
            prof["ingest"] += time.ticks_diff(t_b, t_a)
            prof["step"] += time.ticks_diff(t_c, t_b)
            prof["sensors"] += time.ticks_diff(t_d, t_c)
            prof["tlm"] += time.ticks_diff(t_e, t_d)
            prof_max = max(prof_max, time.ticks_diff(t_e, t_a))

            next_ms = time.ticks_add(next_ms, period_ms)
            sleep = time.ticks_diff(next_ms, time.ticks_ms())
            if sleep > 0:
                time.sleep_ms(sleep)
            else:
                overrun += 1                      # ลูปตามไม่ทัน
                next_ms = time.ticks_ms()         # รีเซ็ตจังหวะ ไม่สะสมหนี้
            loops += 1
            if loops >= int(cfg.FAST_HZ) * 10:    # รายงานทุก ~10 วินาที
                if overrun > loops // 20:
                    _log("ลูปตามไม่ทัน %d/%d รอบ -> ลด FAST_HZ หรือ FEEDBACK_HZ" % (overrun, loops))
                _log("เวลาเฉลี่ยต่อรอบ (ms): ingest %.1f step %.1f sensors %.1f tlm %.1f | ช้าสุด %.1f | คาบ %d"
                     % (prof["ingest"] / loops / 1000, prof["step"] / loops / 1000,
                        prof["sensors"] / loops / 1000, prof["tlm"] / loops / 1000,
                        prof_max / 1000, period_ms))
                _log("  step แยก (ms): " + " ".join(
                    "%s %.1f" % (k, bot.prof[k] / loops / 1000) for k in robot_mod.PROF_KEYS))
                for k in prof:
                    prof[k] = 0
                for k in bot.prof:
                    bot.prof[k] = 0
                prof_max = 0
                _log("alive seq=%d mode=%s fault=%d | rx_bytes=%d frames_ok=%d crc_bad=%d "
                     "buf=%d cmd_seq=%d ingest_err=%d read_err=%d"
                     % (bot.tlm_seq, bot.mode, bot.fault,
                        getattr(host, "rx_bytes", 0) if host else 0,
                        bot.frames_ok, bot.reader.bad, len(bot.reader.buf),
                        bot.cmd_seq, ingest_err,
                        getattr(host, "read_errors", 0) if host else 0))
                loops = overrun = 0
                gc.collect()
    except KeyboardInterrupt:
        _log("หยุด -- ปลดแรงบิด")
        bot.stop()
        if host is not None:
            host.close()
        print("หยุดแล้ว -- ปลดแรงบิด")
    except Exception as e:
        _log_exc("ลูปพัง", e)
        bot.stop()
        if host is not None:
            host.close()
        raise


if __name__ == "__main__":
    run()
