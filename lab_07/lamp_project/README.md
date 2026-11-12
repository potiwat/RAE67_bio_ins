# Lamp_Robot

## กลุ่มและสมาชิก

**ชื่อกลุ่ม:** ____________________

| ชื่อ-นามสกุล | รหัสนักศึกษา | หน้าที่ |
|---|---|---|
| นายกฤตัชญ์ติณห์ เครือทอง | 6752500223 | ____________________ |
| ____________________ | ____________________ | ____________________ |
| ____________________ | ____________________ | ____________________ |


โคมไฟหุ่นยนต์ที่แสดงอารมณ์ด้วยท่าทางและแสง RGB (แนวเดียวกับ Apple ELEGNT) งานวิชา Bio-Inspired Robotics
การเคลื่อนไหวมาจาก **SO(2) CPG** และอารมณ์มาจาก **ระบบฮอร์โมนเทียม** 5 ตัว (social, novelty, boredom, stress, fatigue)

## ฮาร์ดแวร์

| ส่วน | อุปกรณ์ | ต่อที่ ESP32 (node32s) |
|---|---|---|
| ฐานหมุน | MG996R (ไฟเลี้ยงแยก 5–6 V) | GPIO14 |
| ไหล่ / ศอก / หัวก้ม-เงย / หัวหัน | STS3215 ID 1 / 2 / 3 / 4 ผ่าน Waveshare Bus Servo Adapter | RX2 GPIO16, TX2 GPIO17 (1 Mbps) |
| ToF ฐาน | VL53L0X | Wire SDA 21 / SCL 22 |
| ToF หัว | VL53L0X | Wire1 SDA 32 / SCL 33 |
| ไฟ | WS2812 วงแหวน 32 ดวง | GPIO27 |
| กล้อง | USB webcam บนหัว → แล็ปท็อป | (แล็ปท็อปส่งผลให้ ESP32 ทาง USB serial) |

ทุกบอร์ดและแหล่งจ่ายไฟใช้ GND ร่วมกัน

## โครงสร้าง

```
Lamp/
├── runLAMP.command        ดับเบิลคลิกเพื่อรันทั้งระบบ (ESP32 + กล้อง + GUI)
├── platformio.ini         เฟิร์มแวร์ ESP32 (env: lamp)
├── src/
│   ├── lamp_main.cpp      ค่าจูนทั้งหมด (บนสุด), setup(), loop 20 Hz, คำสั่ง
│   ├── brain.cpp          CPG SO(2) + ฮอร์โมน + อารมณ์ + ท่าทาง   (Week 3, 4)
│   ├── sensors.cpp        ToF: contract → low-pass → hysteresis + dwell, รับข้อมูลกล้อง   (Week 2)
│   ├── motors.cpp         ข้อต่อ, ความปลอดภัย, teach / save ท่า, ไฟ RGB
│   ├── experiment.cpp     log D/E/S, C0/C1, trial, scenario จำลอง
│   └── lamp.h             ชนิดข้อมูลและตัวแปรที่ใช้ร่วมกัน
├── camera/
│   ├── lamp_camera.py     โปรแกรมกล้อง: YOLO11n + ByteTrack, MediaPipe มือ, ตรวจโบกมือ, ส่ง CAM/WAVE
│   ├── gui.py             GUI บนคอม (Tkinter)
│   ├── web.py             GUI หน้าเว็บสำหรับ iPad
│   ├── requirements.txt
│   ├── yolo11n.pt         โมเดลหาคน/ของ (COCO)
│   └── hand_landmarker.task   โมเดลมือ (MediaPipe)
└── docs/
    ├── code_guide.html    อธิบายโค้ดทั้งหมดตาม Week 1–4, Lab 05–07 และส่วนนอกวิชา พร้อมโค้ดจริงและเลขบรรทัด
    ├── issues.md          ปัญหาที่เจอระหว่างทำ สาเหตุ และวิธีแก้
    └── csv_data.pdf / .docx   เอกสารอธิบายข้อมูล CSV ที่บันทึก (รูปแบบรายงานวิจัย)
```

## ติดตั้ง

**1. เฟิร์มแวร์ ESP32** (VS Code + PlatformIO)
```
pio run -e lamp -t upload
```
ต้องปิด runLAMP ก่อนอัปโหลด (พอร์ตใช้ได้ทีละโปรแกรม)

**2. โปรแกรมกล้อง** (macOS, Python 3.10)
```
cd camera
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## รัน

ดับเบิลคลิก `runLAMP.command` จะหาพอร์ต ESP32 และกล้อง USB เอง แล้วเปิด GUI
(การเปิดพอร์ตทำให้ ESP32 รีสตาร์ท เป็นเรื่องปกติ) หลังบูตหุ่นจะไปท่า origin แล้วรอ กด **AUTO** ใน GUI เพื่อเริ่ม

หน้า iPad (Wi-Fi วงเดียวกัน): เปิด URL `http://<ip>:8080/?pin=...` ที่โปรแกรมแสดงตอนเริ่ม
PIN สร้างเองครั้งแรก เก็บใน `camera/settings.json` (ไฟล์นี้ไม่อยู่ใน git)

## การทดลอง (C0 / C1)

- `C0` = threshold เดียว (baseline) · `C1` = hysteresis + dwell (ค่าปกติ)
- **กับคนจริง**: เลือก C0/C1 → ▶ Trial → เล่น 600 s → ■ End
- **จำลอง**: พิมพ์ `scen 41` (หรือ 42, 43) ในช่อง command
- ผลทุกรอบต่อท้ายใน `camera/logs/trials.csv`

## ข้อมูลที่บันทึก

ทุกครั้งที่รัน runLAMP จะบันทึกลง `camera/logs/<วันที่_เวลา>/` (data.csv, events.csv, camera.csv, sent.csv, esp32.txt)
และสรุป trial ลง `camera/logs/trials.csv` รายละเอียดทุกคอลัมน์: [docs/csv_data.pdf](docs/csv_data.pdf)

ในชุดที่ส่ง โฟลเดอร์ log ถูกเปลี่ยนชื่อเป็น `run_01` ถึง `run_36` ตามลำดับที่รัน และคอลัมน์ `log_dir` ใน `trials.csv` ใช้ชื่อใหม่นี้แล้ว

## คำสั่งที่ใช้บ่อย (ช่อง command ใน GUI)

| คำสั่ง | ทำอะไร |
|---|---|
| `stop` / `resume` | หยุดฉุกเฉิน / กลับมาและค้างท่า |
| `auto on` / `auto off` | ให้อารมณ์ขยับหุ่น |
| `emo <name>` / `emo auto` | บังคับอารมณ์ / ให้ฮอร์โมนเลือก |
| `save <emotion>` | บันทึกท่าปัจจุบัน (stop → จัดท่าด้วยมือ → resume → save) |
| `teach <joint>` | สอน origin + ช่วงข้อต่อใหม่ |
| `light on` / `light off` | ไฟวงแหวน |
| `tune <key> <v>` / `tune save` | ค่าจูนสด (GUI ทำให้) |
| `h` | รายการคำสั่งทั้งหมด |
