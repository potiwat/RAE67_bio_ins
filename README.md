# RAE67 bio ins

ชุดแล็บสำหรับรายวิชา Bio Inspired Robotics จัดแต่ละแล็บไว้ในโฟลเดอร์ `lab_xx` เพื่อเพิ่มแล็บถัดไปได้โดยไม่ปะปนกัน

| แล็บ | เนื้อหา | เอกสารเริ่มต้น |
|---|---|---|
| [Lab 02](lab_02/README.md) | Robust Reactive Lamp: sensor uncertainty และ sensorimotor control | [คู่มือนักศึกษา](lab_02/Lab02_Student_Manual_TH.docx) |
| [Lab 03](lab_03/README.md) | SO(2) CPG และการเดินแบบ alternating tripod ของหุ่นยนต์หกขา | [คู่มือนักศึกษา](lab_03/Lab03_Student_Manual_TH.docx) |
| [Lab 04](lab_04/README.md) | Artificial Hormone Mechanism: stimulus, hormone dynamics, receptor และ bounded mapping | [ใบงาน Word](lab_04/Lab04_Student_Worksheet_TH.docx) |
| [Lab 05](lab_05/README.md) | Hormone → SO(2) CPG: comparison, timing/fault, one-factor และ synthetic contact | [ใบงาน Word](lab_05/Lab05_Student_Worksheet_TH.docx) / [PDF](lab_05/Lab05_Student_Worksheet_TH.pdf) |
| [Lab 06](lab_06/README.md) | Emotion FSM: interaction, movement/RGB, paired C0/C1 และ replay | [ใบงาน Word](lab_06/Week06_Student_Worksheet_TH.docx) |
| [Lab 07](lab_07/README.md) | ROS 2 interface: seven topics, paired offline trials และ experimental design | [ใบงาน Word](lab_07/Week07_Student_Worksheet_TH.docx) |

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

## เริ่ม Lab 06

```sh
git clone https://github.com/potiwat/RAE67_bio_ins.git
cd RAE67_bio_ins/lab_06
python3 lab06.py --policy student --condition all --repeats 3 --output-dir results/starter
python3 check_submission.py --contract group
```

ใช้ Python 3.10 ขึ้นไปและ standard library เท่านั้น บน Windows ใช้ `py -3` แทน `python3` ได้ หากมี checkout เดิมให้เก็บงานของตนเองแล้ว `git pull --ff-only` ที่ root ก่อนเข้า `lab_06`

อ่าน [คู่มือ Lab 06](lab_06/README.md) และ [ใบงาน Word](lab_06/Week06_Student_Worksheet_TH.docx) เติม TODO ใน `student_policy.py` แล้วตรวจ checker ตาม contract ที่เลือก Starter รันได้แต่ยังไม่ครบจึงควร FAIL ก่อนเติม TODO ใช้ชื่อ output ใหม่ทุกครั้งเพื่อรักษา raw traces เดิม

Lab06 เป็น proposed course model แบบ FSM กฎคงที่ เปรียบเทียบ C0 raw กับ C1 debounce/hysteresis และวัด applied software output onset ด้วยเวลาเสมือน ผลนี้ไม่ยืนยัน physical latency หรือการเรียนรู้ ชุดสาธารณะไม่รวมเฉลย reference policy tests หรือผลผู้สอน

## เริ่ม Lab 07

```sh
git clone https://github.com/potiwat/RAE67_bio_ins.git
cd RAE67_bio_ins/lab_07
python3 offline_lab.py --condition all --repeats 3 --output-dir results/starter_run
python3 check_submission.py --contract group
python3 check_proposal.py proposal.json
```

ใช้ Python 3.10 ขึ้นไปและ standard library สำหรับ offline บน Windows ใช้ `py -3` แทน `python3` ได้ หากมี checkout เดิมให้เก็บงานของตนเองแล้ว `git pull --ff-only` ที่ root ก่อนเข้า `lab_07`

อ่าน [คู่มือ Lab 07](lab_07/README.md) และ [ใบงาน Word](lab_07/Week07_Student_Worksheet_TH.docx) เติม TODO ใน `lamp_week07/student_policy.py` และ proposal ก่อนส่ง checker ของ starter ควร FAIL จนกว่างานส่วนนี้ครบ ใช้ Lab07 starter ได้เอง หรือใช้ policy ของกลุ่มที่ทำเสร็จจาก Lab06 ตามคู่มือ

Lab07 เป็น proposed course model เปรียบเทียบ C0 ideal delivery กับ C1 modeled jitter/drop ด้วยเวลาเสมือน ผล offline ไม่ใช่ ROS/DDS หรือ physical latency benchmark ส่วน ROS 2 adapter source ต้องใช้เครื่อง Ubuntu 24.04 + ROS 2 Jazzy ที่เตรียมไว้แล้ว ชุดสาธารณะไม่รวมเฉลย reference policy tests หรือผลทดลองของผู้สอน
