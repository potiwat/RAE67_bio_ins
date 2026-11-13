# งานส่งกลุ่ม ภาคีนกอีก๋อย — Lab 02–07 และ Mini Project โคมน้อย

| ชื่อ-นามสกุล | รหัสนักศึกษา |
|---|---|
| วทัญญู ชำนาญ | 6752500096 |
| ณัฐพงศ์ เวชยานนท์ | 6752500177 |
| นิธิวัฒน์ สุทธิ | 6752500037 |
| ปุญญพัฒน์ ปราณีชาติ | 6752500355 |

**คลิปสาธิตโคมน้อย:** https://youtu.be/3c7b2VZ8K7c

## ตำแหน่งงานแต่ละแล็บ

คำตอบใบงานทุกแล็บใช้ชื่อเดียวกัน: `LabXX_Student_Manual_TH_answered.docx`

| แล็บ | คำตอบใบงาน | รายงาน | โค้ดที่เติม | ผลการทดลอง | ตัวตรวจ |
|---|---|---|---|---|---|
| 02 Robust Reactive Lamp | `lab_02/submission/Lab02_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_02/submission/report.docx` | `lab_02/student_controller.py` | `lab_02/submission/` (CSV ทุก trial, figures) | grade 10/10 |
| 03 SO(2) CPG | `lab_03/submission/Lab03_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_03/submission/report.docx` | `lab_03/student_cpg.py` | `lab_03/submission/` | grade 5/5 |
| 04 Artificial Hormone | `lab_04/Lab04_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_04/Lab04_Report.docx` | `lab_04/student_hormone.py` | `lab_04/results/` | 13/13 |
| 05 Hormone → CPG | `lab_05/Lab05_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_05/Lab05_Report.docx` | (runner) | `lab_05/results/` | — |
| 06 Emotion & Interaction | `lab_06/Lab06_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_06/Lab06_Report.docx` | `lab_06/student_policy.py` | `lab_06/results/` | 40/40 (baseline + group) |
| 07 ROS 2 + Proposal | `lab_07/Lab07_Student_Manual_TH_answered.docx` (+ `worksheet.md`) | `lab_07/Lamp_Week07_Proposal.docx`, `proposal.json` | `lab_07/lamp_week07/student_policy.py`, `completed_policy.py` | `lab_07/results/` | 40/40, proposal PASS |
| Mini Project | — | `project_komnoi/README.md`, `HANDOVER.md`, `QUICKSTART_TH.md` | `project_komnoi/` (ESP32 MicroPython + สมอง Python + เว็บแดชบอร์ด) | คลิปด้านบน | 64 + 42 tests |

ใบงานแม่แบบของผู้สอน (`Week06_Student_Worksheet_TH.docx`, `Week07_Student_Worksheet_TH.docx` ฯลฯ) คงไว้ตามเดิม ไม่ได้แก้

## หมายเหตุการแก้ไขก่อนส่ง

- `lab_04/student_hormone.py`: ลบตัวอักษรเกินท้ายบรรทัด 32 ที่ทำให้ SyntaxError (sha256 ใหม่ bc215a2e08bf8efe…) ;
  รันซ้ำแล้ว metric ใน `lab_04/results/` ตรงเดิม ต่างเฉพาะหลักที่ 15 ของทศนิยมจากเวอร์ชัน Python
- `lab_07/proposal.json`: กรอกตามแบบการทดลองใน `Lamp_Week07_Proposal.docx` (C0 / delay-only / drop-only) ; check_proposal ผ่าน
- `lab_07/Lamp_Week07_Proposal.docx`: เติมช่องที่ค้าง (แหล่งอ้างอิงชีววิทยา, สมการ AHM และค่า τ/g จาก Lab04, การเชื่อมต่อ, รุ่นอุปกรณ์, อุปกรณ์วัด onset)
- ใส่ชื่อสมาชิกทั้ง 4 คนในทุกรายงาน/ใบงาน และแก้ชื่อกลุ่ม/ชื่อที่สะกดผิด
- `.gitignore`: เพิ่มข้อยกเว้นให้ `lab_04–07/results/` ที่รายงานอ้างถึงขึ้น GitHub ได้ (กติกาเดิมยังตัดผลรันอื่นตามปกติ)
- ลบสำเนาไฟล์ใบงาน Lab 02/03 ที่ซ้ำกันทุกไบต์ และ `__pycache__`

- `lab_07/Lab07_Student_Manual_TH_answered.docx`: เติมค่าเริ่ม CPG และ SHA256 ของ policy ที่ค้าง และติ๊กเช็กลิสต์ 4 ข้อที่ proposal มีครบแล้ว
- ตั้งชื่อคำตอบใบงาน Lab 04–07 ให้เป็นแบบเดียวกับ Lab 02–03 และแยกฉบับที่ตอบแล้วของ Lab 06 ออกจากแม่แบบของผู้สอน

> **การใช้ AI:** ใช้ Claude (Anthropic) ช่วยพัฒนาโค้ดโปรเจกต์โคมน้อย และช่วยตรวจ/แก้ไฟล์ส่งงานตามหมายเหตุข้างบน
> กลุ่มตรวจทานและรับผิดชอบเนื้อหาทั้งหมด (ปรับข้อความนี้ตามกติกาวิชา)
