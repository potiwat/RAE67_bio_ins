"""ดึงบอร์ดกลับมาที่ REPL (ใช้ตอนโคมรันโหมด stdio/USB แล้ว mpremote เข้าไม่ได้ "could not enter raw repl")

    python break_in.py --port COM5

ทำอะไร: รีเซ็ตบอร์ดผ่านสาย USB (ขา RTS -> EN ของ ESP32 DevKit) แล้วยิง Ctrl-C รัวๆ
ช่วงบอร์ดบูตมีหน้าต่างยกเลิก 5 วินาที -> โดน Ctrl-C แล้วหยุด กลับไปที่ >>>
จากนั้นใช้ mpremote ได้ตามปกติ (fs cp / repl) -- ปิดโปรแกรมอื่นที่ใช้พอร์ตนี้ก่อน (sensor_bridge, mpremote)
"""
import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="เช่น COM5")
    ap.add_argument("--seconds", type=float, default=10.0)
    a = ap.parse_args()
    import serial

    try:
        s = serial.Serial(a.port, 115200, timeout=0)
    except Exception as e:
        raise SystemExit("เปิด %s ไม่ได้: %s\n(ปิด sensor_bridge / mpremote ที่ใช้พอร์ตนี้อยู่ก่อน)" % (a.port, e))
    print("รีเซ็ตบอร์ด...")
    s.dtr = False                 # GPIO0 สูง = บูตปกติ (ไม่เข้าโหมดแฟลช)
    s.rts = True                  # EN ต่ำ = รีเซ็ต
    time.sleep(0.15)
    s.rts = False
    print("ยิง Ctrl-C ระหว่างบอร์ดบูต...")
    seen = b""
    t0 = time.time()
    ok = False
    while time.time() - t0 < a.seconds:
        s.write(b"\x03")
        time.sleep(0.05)
        seen = (seen + s.read(4096))[-4000:]
        if b">>> " in seen or "ยกเลิกแล้ว".encode("utf-8") in seen:
            ok = True
            # ยิงต่ออีกนิด กันกรณีเพิ่งเข้า main.py
            for _ in range(10):
                s.write(b"\x03")
                time.sleep(0.05)
            break
    s.write(b"\r\n")
    time.sleep(0.2)
    seen += s.read(4096)
    s.close()
    if ok:
        print("กลับมาที่ REPL แล้ว -- ใช้ mpremote ได้เลย เช่น  mpremote connect %s fs cp motion.py :" % a.port)
    else:
        print("ยังไม่เห็น >>> -- ลองรันอีกครั้ง ; ถ้าไม่ได้ ให้ถอด/เสียบ USB แล้วรันคำสั่งนี้ทันที")
        tail = seen[-300:].decode("utf-8", "replace")
        print("---- ข้อความล่าสุดจากบอร์ด ----\n" + tail)


if __name__ == "__main__":
    main()
