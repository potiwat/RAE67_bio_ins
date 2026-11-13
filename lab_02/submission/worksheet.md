# Lab02 ใบงานบันทึกผล

ชื่อกลุ่ม: ภาคีนกอีก๋อย  สมาชิก: วทัญญู ชำนาญ (6752500096), ณัฐพงศ์ เวชยานนท์ (6752500177), นิธิวัฒน์ สุทธิ (6752500037), ปุญญพัฒน์ ปราณีชาติ (6752500355)  วันที่: 11 พฤศจิกายน 2569

ตัวเลขทั้งหมดคัดจาก `summary_aggregate.csv` (mean ± SD, n = 5 trials ต่อแถว) ไม่ได้ประมาณขึ้นเอง · prediction อยู่ใน `01_prediction.md` (บันทึก 22:11 ก่อนเติม TODO และก่อนรัน)

## ขั้นที่ 1 สมมติฐานก่อนรัน

ดู `01_prediction.md` (ข้อ 1–5) ไม่มีการแก้หลังเห็นผล การเทียบผลกับ prediction อยู่ท้ายใบงานนี้

## ขั้นที่ 2–3 เตรียมโปรแกรมและเติม controller

- `student_controller.py`: TODO 1 EMA filter (ค่าแรกใช้ raw เป็นค่าเริ่ม), TODO 2 single threshold, TODO 3 hysteresis 0.32/0.38 m, TODO 4 u = clamp(Kp·(0.35 − d̂), −0.6, 0.6)
- `grade_submission.py` → `student_grade.json`: **PASS 10 / FAIL 0**
- `python -m unittest discover -s tests -v` → `unittest_output.txt`: 10 ผ่าน, 2 FAIL คือ `test_unfinished_starter_fails_before_writing_results` และ `test_diagnostic_report_identifies_unfinished_starter` ซึ่งตรวจว่า **starter ที่ยังไม่เติม** ต้อง fail จึง fail ตามที่ออกแบบเมื่อชี้ไปที่ไฟล์ที่เติมแล้ว
- โหมด student ให้ metric ทุก trial ตรงกับโหมด reference (`student_comparison/summary_trials.csv` = `reference_comparison/summary_trials.csv` ทุกคอลัมน์ยกเว้น trial_id)

## ขั้นที่ 4 ทดลอง A (σ = 0.01 m, delay 0 ms, 5 trials/condition) — `student_comparison/`

| Condition | Latency enter mean ± SD (s) | False trigger (ครั้ง/นาที) | Extra switches | Mean \|Δu\| |
|---|---|---|---|---|
| C0 | 0.003 ± 0.000 | 3.00 ± 0.00 | 0.0 ± 0.0 | 0.00120 |
| C1 | 0.019 ± 0.026 | 8.39 ± 5.76 | 12.4 ± 2.6 | 0.00864 |
| C2 | 0.407 ± 0.043 | 0.00 ± 0.00 | 0.0 ± 0.0 | 0.00120 |
| C3 | 0.043 ± 0.024 | 1.80 ± 1.64 | 1.6 ± 0.9 | 0.00465 |

ค่าเสริม: latency exit C0 2.857, C1 0.029, C2 0.453, C3 0.089 s · recovery time C0 2.857, C1 0.181, C2 0.454, C3 0.109 s

Controller ที่เลือกทดสอบ robustness: **C2** (ตามคู่มือ) เหตุผล: ต้องการดูว่า filter + hysteresis ยังกัน false trigger ได้ไหมเมื่อ noise เพิ่ม และ latency ที่จ่ายไปเปลี่ยนตาม delay อย่างไร **รันเพิ่ม** C1 และ C3 ด้วย robustness-full ชุดเดียวกัน (`c1_full/`, `c3_full/`) เพื่อทดสอบ prediction ข้อ 1 และ 4 ซึ่งชุดของ C2 ตอบไม่ได้

จำนวน invalid samples: 0 ที่ delay 0 ms; 5 ต่อ trial ที่ 100 ms; 15 ต่อ trial ที่ 300 ms (ทุกตัวเป็น `MISSING_OR_DELAY_BUFFER` ช่วง 0–0.28 s ก่อน sensor buffer เต็ม) จำนวน trial ที่ exclude: **0** เหตุผล: invalid samples อยู่ก่อน physical crossing แรก (6.857 s) มาก ไม่กระทบ metric และ controller ตอบด้วย safe command 0 ตามที่กำหนด

## ขั้นที่ 5 ทดลอง B — `c2_short/` (15 trials), `c2_full/` (45), เพิ่ม `c1_full/` (45), `c3_full/` (45)

| σ (m) / delay (ms) | C2 latency enter (s) | C2 extra / FT | C1 latency enter (s) | C1 recovery (s) | C1 extra / FT (/min) | C3 extra |
|---|---|---|---|---|---|---|
| 0.00 / 0 | 0.423 ± 0.000 | 0 / 0 | 0.003 | 0.017 | 0 / 0 | 0 |
| 0.00 / 100 | 0.523 ± 0.000 | 0 / 0 | 0.103 | 0.117 | 0 / 0 | 0 |
| 0.00 / 300 | 0.723 ± 0.000 | 0 / 0 | 0.303 | 0.317 | 0 / 0 | 0 |
| 0.01 / 0 | 0.431 ± 0.050 | 0 / 0 | 0.015 ± 0.018 | 0.158 ± 0.059 | 12.0 / 12.6 | 1.6 |
| 0.01 / 100 | 0.487 ± 0.043 | 0 / 0 | 0.075 ± 0.030 | 0.255 ± 0.079 | 10.0 / 7.8 | 1.2 |
| 0.01 / 300 | 0.703 ± 0.065 | 0 / 0 | 0.183 ± 0.108 | 0.451 ± 0.065 | 10.0 / 7.3 | 1.2 |
| 0.03 / 0 | 0.407 ± 0.033 | 0 / 0 | 0.047 ± 0.041 | 0.535 ± 0.225 | 39.2 / 32.4 | 8.0 |
| 0.03 / 100 | 0.423 ± 0.117 | 0 / 0 | 0.015 ± 0.018 | 0.562 ± 0.086 | 30.8 / 26.5 | 5.2 |
| 0.03 / 300 | 0.599 ± 0.093 | 0 / 0 | 0.023 ± 0.028 | 0.766 ± 0.195 | 37.6 / 27.4 | 8.0 |

ชุดย่อ `c2_short` ให้ผลทิศทางเดียวกัน (เช่น σ 0.01/300 ms: 0.736 ± 0.012 s, n = 3)

## ขั้นที่ 6 กราฟ (`figures/`)

- `fig1_C1_trial.png`, `fig2_C2_trial.png`: trial ตัวแทน C1_r01 และ C2_r01 (seed เดียวกัน) เส้นประดำ = เวลาที่ระยะจริงข้าม 0.35 m (6.857 s และ 13.143 s) เส้นม่วง = first correct response แยก enter/exit
- `fig3_C1_vs_C2_zoom.png`: ซูม ±0.6 s รอบ crossing ทั้งสองขา
- `fig4_noise_sweep.png`, `fig5_delay_sweep.png`, `fig6_C3_command.png`, `block_diagram.png`

## คำถามวิเคราะห์

**1. C1 กับ C2 ต่างกันด้าน extra switches และ latency เท่าใด**
ที่ σ = 0.01 m, delay 0: extra switches C1 12.4 ± 2.6 เทียบกับ C2 0.0 ± 0.0 ครั้งต่อ trial และ false trigger 8.39 เทียบกับ 0 ครั้ง/นาที แลกกับ latency enter 0.019 ± 0.026 s (C1) เทียบกับ 0.407 ± 0.043 s (C2) คือช้าลง ≈ 0.39 s และ exit 0.029 เทียบกับ 0.453 s แต่ถ้าวัดเป็น recovery time (state ถูกต้องต่อเนื่อง 0.5 s) ต่างกันแค่ 0.181 กับ 0.454 s เพราะ C1 สลับไปมาราว ±0.2 s รอบ crossing ก่อนจะนิ่ง (fig3)

**2. noise 0.01 กับ 0.03 m ส่งผลต่อ metric ใดชัดที่สุด**
extra switches และ false trigger ของ C1 (12.0 → 39.2 ครั้ง, 12.6 → 32.4 ครั้ง/นาที, delay 0) และ recovery time ของ C1 (0.158 → 0.535 s) C3 เพิ่มตาม (extra 1.6 → 8.0) ส่วน C2 ไม่เปลี่ยน: extra = 0 และ false trigger = 0 ทั้ง 9 combinations, latency enter 0.431 → 0.407 s (ต่างไม่เกิน SD) Mean |Δu| ของ C1 เพิ่มจาก 0.008 เป็น 0.025 ตามจำนวนการสลับ (หมายเหตุ: C1 σ 0.01/0 ms ใน `c1_full` ใช้ seed 202618–202622 ส่วนขั้น A ใช้ 202608–202612 false trigger จึงต่างกัน 12.6 กับ 8.39 ครั้ง/นาที ซึ่งอยู่ภายใน SD ≈ 5.8 ของแต่ละชุด)

**3. delay 300 ms ทำให้ latency เพิ่มใกล้ 300 ms หรือไม่**
ที่ σ = 0 เพิ่ม **พอดี 0.300 s** ทุก controller (C1 0.003 → 0.303, C2 0.423 → 0.723, C3 0.063 → 0.363 s) เพราะ delay เป็น FIFO ที่เลื่อนข้อมูลทั้งชุด 15 sample โดยไม่เปลี่ยนรูป เมื่อมี noise การเพิ่มน้อยกว่า 0.3 s: C2 +0.27 s (σ 0.01) และ +0.19 s (σ 0.03, SD 0.09 s, n = 5) เพราะ noise ทำให้แต่ละ trial ข้าม T_enter เร็ว/ช้าต่างกันมาก และ `lab02.py` ให้ seed ต่อเนื่องข้าม combination (seed_base + ลำดับ trial) ดังนั้น trial ที่ delay 0 กับ 300 ms ไม่ได้ใช้ noise ชุดเดียวกัน การเทียบ delay เมื่อมี noise จึงไม่ใช่ paired comparison และ n = 5 ยังน้อยเกินจะสรุปว่าผลน้อยกว่า 0.3 s จริง C1 ที่ σ = 0.03 m latency enter ไม่เพิ่มเลย (0.047 → 0.023 s) เพราะ metric นี้วัด "sample ที่ถูกครั้งแรก" ซึ่งเกิดจาก noise ทำให้ raw ต่ำกว่า T เป็นครั้งคราวก่อนข้อมูลจริงมาถึง ไม่ใช่การตอบสนองที่เร็วจริง recovery time ของ C1 จึงเพิ่ม 0.535 → 0.766 s แทน (fig5)

**4. C3 ชน command limit ช่วงใด และเหตุใด smoothness อย่างเดียวไม่พอ**
C3 **ไม่ชน** limit ±0.6 เลยใน 50 trials ของ C3 (5 ในขั้น A + 45 ใน `c3_full`) ช่วง u อยู่ที่ −0.5995 ถึง +0.299 เพราะ u = 2(0.35 − d̂) และ d̂ อยู่ราว 0.24–0.65 m ค่าที่ใกล้ limit ที่สุด (−0.5995) เกิดที่ sample แรกที่ valid (0.10 s ใน C3 σ 0.03 / 100 ms r02) ซึ่ง filter ถูก initialise จาก raw ค่าเดียวที่ยังไม่ถูกเฉลี่ย (fig6) smoothness อย่างเดียวไม่พอ: C0 และ C2 มี Mean |Δu| เท่ากัน (0.0012) แต่ C0 ออกจาก NEAR ช้า 2.857 s และมี false trigger 3.0 ครั้ง/นาที เพราะไม่ใช้ sensor เลย ส่วน C3 มี Mean |Δu| สูงกว่า (0.0047) เพราะ noise ผ่าน filter เข้า command โดยตรง แต่ตาม distance ได้ต่อเนื่อง ต้องอ่านคู่กับ latency, false trigger และ tracking

## เทียบผลกับ prediction (`01_prediction.md`)

| ข้อ | คาด | ผล | สรุป |
|---|---|---|---|
| 1 C1 extra switches | 0 / ≈12 / 35–40 | 0 / 12.0 / 39.2 | ตรง (ค่า σ 0.01 เคยเห็นมาก่อน ไม่นับเป็นหลักฐาน) |
| 1 C1 false trigger σ 0.03 | 22–28 /min | 32.4 ± 5.8 /min | **ผิด** สูงกว่าที่คาด |
| 1 delay ไม่เปลี่ยน switching | ไม่เปลี่ยน | σ 0.01: 12.0/10.0/10.0, σ 0.03: 39.2/30.8/37.6 | ตรงคร่าว ๆ ส่วนต่างอยู่ในช่วง 1–2 SD |
| 2 C2 FT/extra = 0 ที่ σ 0.03 | 0 / 0 | 0 / 0 ทุก combination | ตรง |
| 2 C2 latency σ 0.03 | mean 0.35–0.42, SD ≈ 0.1 s | 0.407 ± 0.033 s | mean ตรง, **SD ผิด** (เล็กกว่าที่คาด 3 เท่า) |
| 3 delay บวกเพิ่มตรง ๆ | C2 0.50 / 0.70 s | σ 0: 0.523 / 0.723; σ 0.01: 0.487 / 0.703 | ตรงที่ σ 0; มี noise เพิ่มน้อยกว่า delay |
| 3 C1 latency 300 ms | 0.25–0.30 s (σ 0.01) | 0.183 ± 0.108 s | **ผิด** ต่ำกว่า เพราะ noise ให้ sample ถูกก่อนเวลา |
| 3 invalid samples | 5 / 15 | 5 / 15 | ตรง |
| 4 C3 ไม่ชน clamp | ไม่ชน | ไม่ชน (min −0.5995) | ตรง แต่ไม่ได้คาดว่าค่าที่ใกล้สุดมาจาก filter initialisation |
| 5 C0 | 0.003 s, 2.86 s, 3.0 /min, 0.0012 | 0.003, 2.857, 3.00, 0.0012 | ตรง (คำนวณได้แน่นอนเพราะไม่ใช้ sensor) |
