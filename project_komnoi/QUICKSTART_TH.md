# โคมน้อย -- คู่มือใช้งานฉบับย่อ

สองเครื่อง: **เครื่องหลัก** (มีโค้ด ใช้ส่งไฟล์ขึ้นบอร์ดผ่าน USB COM5) และ **เครื่องสมอง** (ต่อ WiFi ของโคม รันสมอง + เว็บ)
เครื่องเดียวก็ได้ ถ้าไม่ต้องใช้อินเทอร์เน็ตระหว่างรัน

---

## เปิดใช้งานประจำวัน

1. เปิดไฟเซอร์โว **ประคองแขน**
2. เครื่องหลัก: `mpremote connect COM5 repl` -> **Ctrl-C** -> **Ctrl-D** -> รอ 5 วินาที -> **Ctrl-]**
   (ไฟวงแหวนขาวกะพริบช้า = บอร์ดทำงาน รอสมอง)
3. เครื่องสมอง: ต่อ WiFi **lamp-robot** รหัส **lamp12345** แล้วในโฟลเดอร์ `lamp`:
   ```
   python sensor_bridge.py
   ```
   บรรทัดแรกขึ้นเวอร์ชัน (ตอนนี้ r19) และเบราว์เซอร์เปิด http://localhost:8080 ให้เอง
4. ปิด: กด `q` ในหน้าต่าง sensor_bridge -> **ประคองแขน** -> ปิดไฟเซอร์โว

ตัวเลือกที่มีประโยชน์:
- `--day-hours 0.05` = วันละ 3 นาที (สาธิตความง่วงสะสม)
- `--sim --dry-run` = ทดลองสมองโดยไม่ต่อโคม (เซนเซอร์จำลอง)
- `--web-port 0` = ไม่เปิดเว็บ

log ทุกครั้งอยู่ที่ `lamp/logs/run_*.csv` (ฮอร์โมน สิ่งเร้า อารมณ์ พารามิเตอร์ ทุก 0.1 วิ) ใช้ทำกราฟรายงาน

---

## ลงโค้ดใหม่ทั้งชุด

**บอร์ด** (เครื่องหลัก ที่ `lamp_firmware\` ปิดไฟเซอร์โวก่อน):
```
mpremote connect COM5 fs cp config.py joints.py keypad.py led.py link.py moisture.py motion.py robot.py safety.py scs.py sensors.py ultrasonic.py :
mpremote connect COM5 fs cp tools/__init__.py tools/all.py tools/check.py tools/jointcal.py tools/keys.py tools/poses.py tools/recenter.py tools/ring.py tools/rollcal.py :tools/
mpremote connect COM5 fs cp tools/scanall.py tools/sense.py tools/servos.py tools/smooth.py tools/teach.py tools/teachhead.py tools/watch.py tools/wizard.py :tools/
mpremote connect COM5 fs cp main.py :main.py
```
**สมอง**: ลบโฟลเดอร์ `lamp` เดิม (สำรอง `lamp/logs` ก่อน) แล้วก็อป `lamp` ชุดใหม่ลงไป

แก้ `link.py` เมื่อไร ต้องลงทั้งสองฝั่ง (ไฟล์ต้องเหมือนกัน) ไม่งั้นบอร์ดเข้าโหมดปลอดภัย (ไฟขาวกะพริบ)

---

## เครื่องมือบนบอร์ด (REPL: Ctrl-C -> Ctrl-D -> Ctrl-C แล้ว `import tools.xxx`)

| คำสั่ง | ใช้ทำอะไร | ขยับไหม |
|---|---|---|
| `tools.servos` | เซอร์โวตอบกี่ตัว มุม ไฟ อุณหภูมิ (`tools.servos.run(scan=True)` หา ID แปลก) | ไม่ |
| `tools.check` | ทดสอบทุกข้อต่อไปขอบบน-ล่าง (`tools.check.one("elbow")` ข้อเดียว) | ขยับ |
| `tools.watch` | ดูค่าข้อต่อเดียวสดๆ ตอนหมุนด้วยมือ (`tools.watch.run(2)`) | ไม่ (ปลดแรงบิด) |
| `tools.poses` | วนดูท่าทุกอารมณ์ | ขยับ |
| `tools.teach` | จับหุ่นจัดท่าเอง แล้วจดมุมเป็นตารางท่า | ปลดแรงบิด |
| `tools.teachhead` | ล็อกตัวท่าหลับ จับหัวจัดเอง (ท่าแอบดู) | ตัวค้าง หัวหลวม |
| `tools.jointcal` | คาลิเบรตข้อต่อเดียว (ไม่เขียน calib.py) | ปลดแรงบิด |
| `tools.recenter` | หมุนแกนเปล่าไปจุด 0 เพื่อประกอบ horn ใหม่ | ขยับแกน |
| `tools.sense` / `tools.keys` / `tools.ring` | ทดสอบเซนเซอร์ / keypad / ไฟวงแหวน | ไม่ |

**ห้าม** `tools.wizard` กับข้อต่อเดียว (เขียน calib.py ทับทั้งไฟล์)

---

## แก้ปัญหาที่เจอบ่อย

| อาการ | ทำอย่างนี้ |
|---|---|
| `mpremote` ขึ้น "could not enter raw repl" | บอร์ดอยู่โหมด USB (stdio): `python lamp/break_in.py --port COM5` แล้วลองใหม่ |
| เว็บขึ้น "โคมไม่ตอบ" | เครื่องสมองยังไม่ได้ต่อ WiFi lamp-robot หรือบอร์ดยังไม่เริ่ม (ข้อ 2 ด้านบน) |
| `link OK` แต่ไม่มีค่าระยะ | Windows Firewall: อนุญาต Python ทั้ง Private และ Public |
| ไฟขาวกะพริบตลอด | ยังไม่มีสมองต่อ หรือ link.py สองฝั่งไม่ตรงกัน |
| `undervolt` / `fb_lost` / แขนยวบ | ไฟเลี้ยงเซอร์โวตก -- เช็คแหล่งจ่าย ลดแรงสะดุ้งใน motion.py (ENTER_KICKS "Fear") |
| ข้อต่อวิ่งผิดทาง ค้าง load 1000 | **ตัดไฟทันที** แล้ว `tools.servos` ดู tick ถ้าชิด 0 หรือ 1022 = horn รูด/แกนหลุดช่วง -> `tools.recenter` |
| หัว/แขนไม่ตรงท่าที่อยากได้ | `tools.teach` / `tools.teachhead` จัดเองแล้วใส่ตัวเลขใน motion.py **และ** lamp/lamp.py ให้ตรงกัน |

---

## ปรับพฤติกรรมเอง (แก้แล้วรัน `python lamp/test_lamp.py` ให้ผ่าน)

| อยากปรับ | ไฟล์ / ค่า |
|---|---|
| ระยะตรวจจับ | `lamp/sensor_perception.py` `zone_far_m` (0.70), `present_release_m` (0.85) |
| สนใจ / ผูกพัน เร็ว-ช้า | `lamp/behavior.py` `target_min_dwell`, `curious_min_h`, `engage_affinity`, `engage_after_s` |
| กลัวง่าย-ยาก | `behavior.py` `startle_h_enter`, `reflex_enter` ; `sensor_perception.py` `fear_speed_lo/hi`, `alarm_hold_s` |
| ป่วย | `behavior.py` `sick_enter`, `sick_release`, `sick_sleep_extra`, `sick_curiosity_cut` |
| หลับ | `behavior.py` `sleep_min_s` (480), `awake_full_s` (12 ชม.), `peek_every_s` (20) |
| ท่าทาง | `lamp_firmware/motion.py` `_POSE_ROWS` + `lamp/lamp.py` `POSES` (ต้องตรงกัน) |
| เต้น / หัวนำ / ป่วยสั่น | `motion.py` `DANCE_*`, `LEAD_ROLL_*`, `SICK_*` |
| สีไฟ | `lamp_firmware/led.py` `EMOTION_RGB`, `CHASE_*`, `SICK_PULSE*` |
