# Lab 03 — ผลส่งมอบ

ไฟล์ทั้งหมดอยู่ใน `lab_03/submission/` (ไม่ใช้ `results/` เพราะ `.gitignore` ของ repo ตัด `results/` ออก ทำให้ raw CSV ไม่ถูก push)

| # | ผลส่งมอบตามคู่มือ | ไฟล์ |
|---|---|---|
| — | Prediction ก่อนทดลอง (เวลาบันทึก) | `01_prediction.md` (บันทึก 2026-11-11 19:13 ก่อนรันโปรแกรม) |
| 1 | `worksheet.md` ที่กรอก prediction และผลวัด | `worksheet.md` (ต้นฉบับเปล่าอยู่ที่ `../worksheet.md`) |
| 2 | `student_cpg.py` ที่เติม TODO ครบ | `../student_cpg.py` |
| 3 | `results/my_grade.json` | `my_grade.json` (PASS 5 / 5) |
| 4 | raw CSV และ summary ของ gait comparison | `gait_comparison/` (`baseline.csv`, `fast.csv`, `high_gain.csv`, `*_summary.json`, `*.svg`, `conditions_summary.csv`) |
| 5 | `week4_bridge.csv` และ `handoff_contract.json` | `week4_bridge/` |
| 6 | กราฟตัวแทนอย่างน้อยสองเงื่อนไข | `figures/fig1_gait_three_conditions.png` (o₁, o₂ + gait diagram ทั้งสาม condition), `figures/fig2_phase_portrait.png`, `figures/fig3_metrics.png`, `figures/fig4_week4_bridge.png` |
| — | Block diagram | `figures/block_diagram.png` |
| 7 | รายงาน 1–2 หน้า | `report.docx` (2 หน้า) |
| — | คู่มือนักศึกษาที่ตอบคำถามครบ (prediction ข้อ 6, ผลขั้น B–D, คำถามวิเคราะห์ข้อ 12 ทั้ง 6 ข้อ, checklist) | `Lab03_Student_Manual_TH_answered.docx` (ต้นฉบับเปล่าอยู่ที่ `../Lab03_Student_Manual_TH.docx`) |

`make_figures.py` อ่านเฉพาะ raw CSV แล้วสร้างกราฟทั้งหมดและ `analysis.json` (amplitude, มุมหมุนต่อ step, คาบเป็นจำนวน step, การตรวจ antiphase, transient ของ bridge) และตรวจว่า `so2_step` / `decode_tripod` ของนักศึกษาให้ค่าตรงกับ raw CSV ของ reference ทุก sample

## รันซ้ำ

จากโฟลเดอร์ `lab_03` (แบบจำลองไม่มี noise ผลจะเหมือนเดิมทุกครั้ง):

```powershell
$env:PYTHONUTF8=1
python grade_submission.py --student-file student_cpg.py --out submission\my_grade.json
python cpg_walk_sim.py --condition all --output-dir submission\gait_comparison
python week4_bridge.py --output-dir submission\week4_bridge
python submission\make_figures.py
```

หมายเหตุ

- `cpg_walk_sim.py` และ `week4_bridge.py` ใช้ `step_cpg` ของตัวเอง ไม่ได้ import `student_cpg.py` จึงตรวจความตรงกันของโค้ดนักศึกษาแยกใน `make_figures.py` (ผลใน `analysis.json` → `student_vs_reference`: ต่างกัน 0.0, contact ไม่ตรง 0 sample)
- ขั้น A (visual simulator `hexapod_cpg_sim.html`) ไม่ได้เปิดใช้งานแบบ interactive ในรอบนี้ ตรวจเพียงโค้ดว่าใช้สมการ tripod sign และ preset เดียวกับ batch ผลหลักทั้งหมดมาจาก batch run ที่ทำซ้ำได้
- `my_grade.json` เก็บ path ของเครื่องที่รัน
