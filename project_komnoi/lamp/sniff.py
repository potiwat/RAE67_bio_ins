"""ดักดูว่าบอร์ดส่งอะไรออกมาทาง serial -- รันบนโน้ตบุ๊ก

    python sniff.py --port COM5

ถอดสาย USB เสียบใหม่ก่อนรัน แล้วดูว่าได้อะไร
"""
import argparse
import time

import serial

HDR = b"\xaa\x55"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--bauds", default="921600,115200")
    args = ap.parse_args()

    for baud in [int(b) for b in args.bauds.split(",")]:
        print("\n=== ฟังที่ baud %d เป็นเวลา %.0f วินาที ===" % (baud, args.seconds))
        try:
            ser = serial.Serial(args.port, baud, timeout=0.1)
        except Exception as e:
            print("เปิดพอร์ตไม่ได้:", e, "(มี REPL หรือ host_bridge ค้างอยู่ไหม)")
            return
        buf = b""
        t0 = time.time()
        while time.time() - t0 < args.seconds:
            d = ser.read(512)
            if d:
                buf += d
        ser.close()

        if not buf:
            print("ไม่ได้อะไรเลย")
            continue
        frames = buf.count(HDR)
        printable = sum(1 for b in buf if 32 <= b < 127 or b in (10, 13))
        print("ได้ %d ไบต์  เฟรม telemetry (AA 55) = %d  อ่านเป็นตัวอักษรได้ %d%%"
              % (len(buf), frames, 100 * printable // max(1, len(buf))))
        print("ตัวอย่าง (hex):", buf[:48].hex(" "))
        text = buf.decode("utf-8", "replace")
        if printable > 50:
            print("-------- ข้อความเต็มจากบอร์ด --------")
            print(text)
            print("------------------------------------")
        else:
            print("ตัวอย่าง (text):", repr(text[:160]))
        if frames:
            print(">>> เจอเฟรม telemetry -- ลิงก์ใช้ได้ที่ baud นี้")
        elif printable > 70:
            print(">>> เป็นข้อความธรรมดา = REPL ยังเกาะ UART0 อยู่ (ปลด REPL ไม่สำเร็จ)")
        else:
            print(">>> เป็นไบต์มั่ว = baud ไม่ตรง")


if __name__ == "__main__":
    main()
