# RAE67 bio ins

ชุดแล็บสำหรับรายวิชา Bio Inspired Robotics จัดแต่ละแล็บไว้ในโฟลเดอร์ `lab_xx` เพื่อเพิ่มแล็บถัดไปได้โดยไม่ปะปนกัน

| แล็บ | เนื้อหา | เอกสารเริ่มต้น |
|---|---|---|
| [Lab 02](lab_02/README.md) | Robust Reactive Lamp: sensor uncertainty และ sensorimotor control | [คู่มือนักศึกษา](lab_02/Lab02_Student_Manual_TH.docx) |
| [Lab 03](lab_03/README.md) | SO(2) CPG และการเดินแบบ alternating tripod ของหุ่นยนต์หกขา | [คู่มือนักศึกษา](lab_03/Lab03_Student_Manual_TH.docx) |
| [Lab 04](lab_04/README.md) | Artificial Hormone Mechanism: stimulus, hormone dynamics, receptor และ bounded mapping | [ใบงาน Word](lab_04/Lab04_Student_Worksheet_TH.docx) |
| [Lab 05](lab_05/README.md) | Hormone → SO(2) CPG: comparison, timing/fault, one-factor และ synthetic contact | [ใบงาน Word](lab_05/Lab05_Student_Worksheet_TH.docx) / [PDF](lab_05/Lab05_Student_Worksheet_TH.pdf) |

## เริ่ม Lab 02

```powershell
cd lab_02
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

เปิด [คำอธิบายแล็บ](lab_02/README.md) สำหรับขั้นตอนทดลองและไฟล์ที่ต้องส่ง ค่า controller ใน repo เป็น proposed course model สำหรับ simulator ไม่ใช่ค่าที่รับรองสำหรับหุ่นยนต์จริง

## เริ่ม Lab 03

```powershell
cd lab_03
python cpg_walk_sim.py --condition baseline --duration 2 --output-dir results\smoke_test
```

เปิด [คำอธิบาย Lab 03](lab_03/README.md) แล้วดาวน์โหลด [คู่มือนักศึกษา](lab_03/Lab03_Student_Manual_TH.docx) ก่อนเริ่มทำ TODO ใน `student_cpg.py`

## เริ่ม Lab 04

```sh
git clone https://github.com/potiwat/RAE67_bio_ins.git
cd RAE67_bio_ins/lab_04
python3 --version
```

ใช้ Python 3.10 ขึ้นไปและ standard library เท่านั้น บน Windows ใช้ `py -3` แทน `python3` ได้ เปิด [คู่มือ Lab 04](lab_04/README.md) และ [ใบงาน Word](lab_04/Lab04_Student_Worksheet_TH.docx) เขียน prediction แล้วเติม TODO ใน `student_hormone.py` ก่อนตรวจและรัน:

```sh
python3 check_submission.py --student-file student_hormone.py
python3 lab04.py --controller-source student --condition all --profile step --output-dir results/comparison
```

starter ที่ยังไม่เติม TODO จะไม่ผ่าน checker โดยตั้งใจ Lab04 วัดการตอบสนองของ hormone subsystem ใน proposed course model ไม่ได้ทดสอบ gait หรือความปลอดภัยของหุ่นยนต์จริง ชุดสาธารณะไม่รวมเฉลยหรือผลทดลองของผู้สอน


## เริ่ม Lab 05

```sh
git clone https://github.com/potiwat/RAE67_bio_ins.git
cd RAE67_bio_ins/lab_05
python3 --version
python3 lab05.py --output-dir results/comparison
python3 contact_demo.py --output-dir results/contact
```

ใช้ Python 3.10 ขึ้นไปและ standard library เท่านั้น Windows ใช้ `py -3` แทน `python3` ได้ หากมี checkout เดิมให้เก็บงานของตนเองแล้ว `git pull --ff-only` ที่ root ก่อนเข้า `lab_05`

อ่าน [คู่มือ Lab 05](lab_05/README.md) และ [ใบงาน Word](lab_05/Lab05_Student_Worksheet_TH.docx) / [PDF](lab_05/Lab05_Student_Worksheet_TH.pdf) ตั้ง prediction ก่อนรัน เปิด `results/comparison/report.html` และ `results/contact/report.html` ด้วย browser

Lab05 เป็น working scaffold สำหรับ prediction/analysis และเป็น proposed course model ที่ใช้ scheduled stimulus กับ kinematic body ส่วน contact demo ใช้ข้อมูลสังเคราะห์แยกจาก controller ยังไม่ใช่ full ALCS/MNLC หรือ terrain feedback ตามบทความ ชุดสาธารณะไม่รวมคู่มือเฉลย tests หรือผลตรวจของผู้สอน
