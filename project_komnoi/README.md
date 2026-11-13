# โคมน้อย (Komnoi) — โคมไฟหุ่นยนต์ 5 ข้อต่อที่มีอารมณ์จากฮอร์โมนเทียม

Mini Project วิชา Bio-Inspired Robotics (RAE67) — โคมแขนกลสไตล์ Luxo Jr. ที่ "รู้สึก" ผ่านระบบฮอร์โมนเทียม (AHM)
และขยับด้วย SO(2) CPG บนหุ่นจริง

**กลุ่ม ภาคีนกอีก๋อย**

| ชื่อ-นามสกุล | รหัสนักศึกษา |
|---|---|
| วทัญญู ชำนาญ | 6752500096 |
| ณัฐพงศ์ เวชยานนท์ | 6752500177 |
| นิธิวัฒน์ สุทธิ | 6752500037 |
| ปุญญพัฒน์ ปราณีชาติ | 6752500355 |

**คลิปสาธิต:** https://youtu.be/3c7b2VZ8K7c

> **การใช้ AI:** โค้ดและเอกสารพัฒนาร่วมกับ Claude (Anthropic) ตลอดโปรเจกต์ กลุ่มทดสอบบนหุ่นจริง ตรวจทาน และรับผิดชอบเนื้อหา

## สถาปัตยกรรม

| ส่วน | โฟลเดอร์ | ภาษา | หน้าที่ |
|---|---|---|---|
| ร่างกาย | `lamp_firmware/` | MicroPython 1.29 บน ESP32 | เซนเซอร์, เซอร์โว Feetech SCS15 ×5, ไฟ NeoPixel, ความปลอดภัย, ท่าทาง + SO(2) CPG (ลูป 30 Hz) |
| สมอง | `lamp/` | Python 3 (stdlib ล้วน) | การรับรู้, ฮอร์โมน 5 ตัว, FSM อารมณ์ 6 แบบ (คิด 10 Hz) |
| ลิงก์ | `link.py` ทั้งสองฝั่ง (ต้องเหมือนกัน) | UDP ผ่าน WiFi AP ของโคม | คำสั่ง 50 Hz, telemetry 20 Hz, CRC |
| หน้าจอ | `lamp/web_ui.py` + `lamp/dashboard.html` | HTML/CSS/JS | http://localhost:8080 ดูค่าสดและกดสั่งโคม |

เริ่มใช้งานและแก้ปัญหา: [`QUICKSTART_TH.md`](QUICKSTART_TH.md) · สถานะและค่าทั้งหมด: [`HANDOVER.md`](HANDOVER.md) (ส่วนบนสุด)

## เชื่อมกับแล็บของรายวิชา

| แล็บ | แนวคิดในแล็บ | ในโคมน้อย |
|---|---|---|
| Lab 02 | low-pass + hysteresis + safe command | `lamp/sensor_perception.py`: median filter 5 ค่า, hysteresis "มีคน" 0.70/0.85 m, ยืนยัน 0.3 s ; `lamp_firmware/safety.py`: soft limit, slew rate |
| Lab 03 | SO(2) CPG `o ← tanh(α·R(φ)·o)` | `lamp_firmware/motion.py` `SO2CPG` (α = 1.01, φ = 2π·0.35 Hz·tempo·dt) สร้างจังหวะหายใจ |
| Lab 04 | AHM: production / clearance / binding + receptor | `lamp/ahm.py`: `H ← clamp(H + αS(1−H) − βH − γH)`, ครึ่งชีวิต 4–90 s, receptor มี threshold |
| Lab 05 | hormone → bounded mapping → CPG | `lamp/behavior.py` `PARAM_SPECS`/`Modulator`: E → tempo (φ) และ amp ของ CPG แบบ slew-limited |
| Lab 06 | FSM อารมณ์ + RGB + debounce/guard | `lamp/behavior.py` FSM (Fear > Sick > Curious/Engage > Idle/Sleep), สี Lab 06 ใน `lamp_firmware/led.py`, afraid guard |
| Lab 07 | interface + experimental design กับหุ่นจริง | proposal ใน `../lab_07/` (ESP32 + micro-ROS, servo SCS15, NeoPixel ของโคมนี้คือฮาร์ดแวร์ฝั่ง real robot) |

กลไกชีววิทยาที่เพิ่มเอง (ได้แรงบันดาลใจ ไม่ใช่แบบจำลองทางชีววิทยาที่พิสูจน์แล้ว): habituation, efference copy, looming,
ความคุ้นเคยสถานที่ (background map), active sensing (หัวนำ ตัวตาม), แอบดูตอนหลับ, sleep pressure 12 ชม., sickness behavior

## ทดสอบ

```
python lamp/test_lamp.py            # 64 tests (สมอง, ซิม, เว็บ)
python lamp_firmware/test_fw.py     # 42 tests (เฟิร์มแวร์บนคอม)
python lamp/sensor_bridge.py --sim --dry-run     # รันสมองกับเซนเซอร์จำลอง + เว็บแดชบอร์ด
```

บนหุ่นจริง: `import tools.check` บน REPL ของบอร์ด ต้องผ่านครบ 5 ข้อต่อ (ดู QUICKSTART)

## เอกสารอื่น

`docs/komnoi_friend_draft.pptx` สไลด์ร่างแรก (สไลด์นำเสนอฉบับจริงอยู่ใน Canva ของกลุ่ม) · `hormone-robot-design-notes.md` เอกสารออกแบบระบบฮอร์โมนตั้งต้น
