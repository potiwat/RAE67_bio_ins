# Lab 02 — ผลส่งมอบ (ทำใหม่ 2026-11-11)

ไฟล์ผลทั้งหมดอยู่ใน `lab_02/submission/` (ไม่ใช้ `results/` เพราะ `.gitignore` ของ repo ตัด `results/` ออก)

| # | ผลส่งมอบตามคู่มือ (ข้อ 13 ใน README) | ไฟล์ |
|---|---|---|
| 1 | Prediction ก่อนทดลอง และบันทึกการแก้ | `01_prediction.md` (บันทึก 2026-11-11 22:11 ก่อนเติม TODO และก่อนรัน ไม่มีการแก้) |
| 2 | Block diagram ของ sensorimotor loop | `figures/block_diagram.png` |
| 3 | `student_controller.py` ที่เติม TODO 1–4 | `../student_controller.py` (ไม่ได้แก้ source อื่น) |
| 4 | ผลตรวจ `grade_submission.py` | `student_grade.json` (PASS 10 / FAIL 0), `unittest_output.txt` |
| 4 | `run_config.json` ของโหมด student, raw CSV ทุก trial, `summary_aggregate.csv` | `student_comparison/` (ขั้น A, 20 trials), `c2_short/` (15), `c2_full/` (45); รันเพิ่ม `c1_full/` (45), `c3_full/` (45); `reference_comparison/` (โหมด reference ใช้เทียบ) |
| 5 | กราฟตัวแทน C1 และ C2 พร้อม physical crossing และ first correct response | `figures/fig1_C1_trial.png`, `figures/fig2_C2_trial.png`, `figures/fig3_C1_vs_C2_zoom.png` |
| — | กราฟวิเคราะห์ noise / delay / C3 | `figures/fig4_noise_sweep.png`, `figures/fig5_delay_sweep.png`, `figures/fig6_C3_command.png` |
| — | ใบงานบันทึกผล + คำถามวิเคราะห์ + เทียบ prediction | `worksheet.md` |
| 6 | รายงาน 1–2 หน้า | `report.docx` (2 หน้า) |
| — | คู่มือนักศึกษาที่ตอบคำถามครบ (สมมติฐาน ขั้นที่ 1, ตารางใบงาน, คำถามวิเคราะห์ 4 ข้อ) | `Lab02_Student_Manual_TH_answered.docx` (ต้นฉบับเปล่าอยู่ที่ `../Lab02_Student_Manual_TH.docx`) |

## รันซ้ำ

Python 3.11.0 + matplotlib จากโฟลเดอร์ `lab_02` (seed เดิม ผลจะเหมือนเดิม):

```sh
python grade_submission.py --student-file student_controller.py --out submission/student_grade.json
python -m unittest discover -s tests -v > submission/unittest_output.txt 2>&1
python lab02.py --controller-source student --student-file student_controller.py --protocol controller-comparison --out submission/student_comparison
python lab02.py --protocol controller-comparison --out submission/reference_comparison
python lab02.py --controller-source student --student-file student_controller.py --protocol robustness-short --condition C2 --out submission/c2_short
python lab02.py --controller-source student --student-file student_controller.py --protocol robustness-full --condition C2 --out submission/c2_full
python lab02.py --controller-source student --student-file student_controller.py --protocol robustness-full --condition C1 --out submission/c1_full
python lab02.py --controller-source student --student-file student_controller.py --protocol robustness-full --condition C3 --out submission/c3_full
python submission/make_figures.py
```

## หมายเหตุ

- ถ้าโฟลเดอร์ผลมีอยู่แล้ว `lab02.py` ต้องใส่ `--overwrite` และ `grade_submission.py` ไม่เขียนทับ `--out` เดิม
- `run_config.json` เก็บ path ของเครื่องที่รัน ใช้ `student_file_sha256` ยืนยันว่าเป็น `student_controller.py` ไฟล์เดียวกัน
- unit test 2 ข้อที่ตรวจว่า starter ยังไม่เสร็จจะ FAIL เมื่อเติม TODO แล้ว ตามที่ออกแบบไว้ อีก 10 ข้อผ่าน
- รอบนี้ทำใหม่ทั้งหมดจาก starter ของผู้สอน ผู้ทำเคยเห็นผลขั้น A ที่ σ 0.01 m จากรอบก่อน จึงระบุไว้ใน `01_prediction.md` ว่า prediction ส่วนนั้นไม่ blind
- ส่วนที่ไม่ได้ทำ: การเชื่อมหุ่นยนต์จริง (README ข้อ 12) เพราะไม่มีฮาร์ดแวร์ และไม่ได้ทดสอบ `invalid_rate > 0` เพราะ protocol ทั้งสามไม่ได้ใช้
