# ใบงาน Lab04 (รายงาน 1–2 หน้า)

ชื่อ: นายกฤตัชญ์ติณห์ เครือทอง รหัสนักศึกษา: 6752500223 code version/hash: commit 2a70638, student_hormone.py SHA256 cf0d7472…69eb060

หมายเหตุ: prediction เขียนหลังจากรันโปรแกรมแล้ว ตัวเลขทุกค่ามาจากการรันจริง (ภาพ Terminal อยู่ใน `figures/` และในใบงาน Word)

## A. ก่อนรัน (10 นาที)

วาด block diagram แล้วเขียนประโยคเชื่อมแต่ละคู่ S, P/C/B, H, R, phi/stride ให้เห็นว่า state เก็บประวัติอย่างไร

```text
S(t) ──k_prod──▶ P ──(+)──┐
                          ▼
H_old ──k_clear──▶ C ──(−)──▶ H_raw = H_old + dt(P − C − B) ──clamp[0,1]──▶ H_new ──receptor──▶ R_new ──bounded map──▶ phi, stride_half
  ▲  └─receptor─▶ R_old ──k_bind──▶ B ──(−)──┘                                  │
  └───────────────────────────── z⁻¹ (เก็บเป็น H_old ของรอบถัดไป) ◀────────────┘
```

- S → P: stimulus เพิ่มอัตราการผลิต hormone ตรงๆ (P = k_prod·S)
- H_old → C และ R_old → B: การสลายและการจับ receptor ใช้ state เก่าของรอบเดียวกัน จึงเป็น feedback เชิงลบ
- P, C, B → H: ผลสุทธิ P−C−B ถูกอินทิเกรตด้วย Euler ทำให้ H เก็บประวัติของ S ในอดีต (มีหน่วยความจำ)
- H → R: receptor normalize และ clamp ให้อยู่ใน [0,1]
- R → phi/stride: bounded mapping เดียวกับ Week 03 ไม่ส่งคำสั่งมอเตอร์โดยตรง

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | ขึ้นเร็วกว่า, AUC สูงกว่า, ชน upper clamp | k_prod 0.8→1.2 ทำให้ P ใหญ่ขึ้น 50% จุดสมดุลเกิน 1 | rise 2.70→1.05 s, latency 0.15→0.10 s, AUC 10.00→10.67, clamp 0→29% ของ updates, recovery เท่ากัน 2.85 s |
| C3 vs C1 | สะสมสูงกว่าและฟื้นตัวช้ากว่า | k_clear 0.6→0.25 ทำให้ C เล็ก จุดสมดุลสูงขึ้นและ time constant ยาวขึ้น | AUC 11.39 (สูงสุด), recovery 2.85→5.10 s, clamp 27.3% |
| C4 vs C1 | สูงกว่าเล็กน้อย ฟื้นช้ากว่าเล็กน้อย | ตัด B (k_bind=0) เหลือ removal แค่ C | AUC 10.75, recovery 3.80 s, clamp 25.8% |
| C0 vs C1 | ตอบทันที ไม่มีหน่วยความจำ | R=S โดยตรง ไม่มี state H | latency 0.05 s (เท่า sampling), rise 0 s, recovery 0.05 s, peak_H = N/A |

เขียนว่า prediction ใดอาจเปลี่ยนเพราะ H มี upper bound=1: **"C2 และ C3 จะมี peak สูงกว่า C1" ไม่เป็นจริง เพราะ C2/C3/C4 ชน bound จน peak_H = 1.0 เท่ากันหมด ต้องแยกด้วย AUC, rise, recovery และ clamp fraction แทน**

## B. เติม code และคำนวณมือ (20 นาที)

1. Source equation (Homchanthanakul et al. 2019): `Hc(t) = beta·Hc(t−1) + Hg(t) − Hr(t)`, `Hg = alpha·f(S)`, `Hr = Σ gamma_i·Receptor_i`
   Proposed course model (Euler): `H_raw = H_old + dt(k_prod·S − k_clear·H_old − k_bind·R_old)`, `H_new = clamp(H_raw, 0, 1)` — ตัวเลขทั้งหมดเป็นค่าสอน ไม่ใช่ค่าจากบทความ
2. receptor(H=.2, H_min=.1, H_max=.5) = (0.2−0.1)/(0.5−0.1) = **0.25**
3. `step` เก็บ `h_old` และ `r_old = receptor(h_old)` ก่อน แล้วคำนวณ P, C, B จากค่าเก่าทั้งหมดก่อน update H ครั้งเดียว
4. H_old=0, S=1, dt=0.05, C1 (k_prod .8, k_clear .6, k_bind .2):
   - รอบ 1: P=0.8, C=0, B=0, H_raw=0+0.05(0.8)=0.0400, H=0.0400, R=0.0400, phi=0.20+0.20(0.04)=0.2080, stride=0.0554
   - รอบ 2: P=0.8, C=0.6(0.04)=0.024, B=0.2(0.04)=0.008, H_raw=0.04+0.05(0.768)=0.0784, H=R=0.0784, phi=0.21568, stride=0.05578
5. `check_submission.py` ผ่านครบ 13 case (receptor normalization/clamp/invalid range, on/off update, old-state, upper clamp, no binding, fault NaN/inf/−0.1/1.1)

| input_time_s | time_s | P | C | B | H_raw | H | R | phi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|10.00|10.05|0.8|0.000|0.000|0.0400|0.0400|0.0400|0.2080|
|10.05|10.10|0.8|0.024|0.008|0.0784|0.0784|0.0784|0.2157|

แถว CSV ที่เลือกสอดคล้องกับ time convention อย่างไร? **แถว time_s=10.05 ใช้ stimulus และ P/C/B ของ input_time_s=10.00 (ต้นช่วง) แล้วเก็บ state หลัง update ที่ปลายช่วง ค่าใน `results/comparison/C1_step.csv` ตรงกับการคำนวณมือ (H=0.0400 และ 0.0784)**

## C. Controlled comparison (20 นาที)

รัน C0–C4 ใช้ dt,duration,H0,stimulus,mapping เดียวกัน เปิด report.html และกรอกค่าจาก metrics.json ไม่อ่านค่าด้วยสายตาอย่างเดียว

| Condition | peak_H | AUC_H | latency s | rise s | recovery s | upper clamp fraction | phi TV rad |
|---|---|---|---|---|---|---|---|
|C0|N/A|N/A|0.05|0.00|0.05|N/A|0.4000|
|C1|0.9997|9.9996|0.15|2.70|2.85|0.0000|0.3998|
|C2|1.0000|10.6724|0.10|1.05|2.85|0.2900|0.3999|
|C3|1.0000|11.3891|0.15|1.45|5.10|0.2733|0.3979|
|C4|1.0000|10.7547|0.15|1.70|3.80|0.2583|0.3995|

- C3 ฟื้นช้ากว่า C1 เท่าไร? **5.10 − 2.85 = 2.25 s (ช้ากว่า ≈1.8 เท่า) เพราะ k_clear ลดจาก 0.6 เป็น 0.25**
- C2/C3 peak เท่ากันหรือไม่ และ metric ใดแยกได้? **peak_H = 1.0 เท่ากันเพราะ clamp แต่แยกได้ด้วย rise (1.05 vs 1.45 s), recovery (2.85 vs 5.10 s) และ AUC (10.67 vs 11.39)**
- C0 มี H หรือไม่? **ไม่มี C0 เป็น direct R=S จึงรายงาน peak_H/AUC เป็น N/A ไม่ใช่ 0**
- TV ที่ต่ำกว่าเพียงอย่างเดียวพิสูจน์คุณภาพ gait ได้หรือไม่? **ไม่ได้ phi TV ทุก condition ≈0.40 rad ใกล้กันมาก (step ขึ้นลงอย่างละครั้ง) TV บอกแค่ปริมาณการเปลี่ยนคำสั่ง ไม่บอกความเสถียรหรือความเร็วการเดิน และ Lab04 ไม่ได้รัน CPG/gait**

## D. Extreme tests และ handoff (10 นาที)

รัน zero,one,spike,fault ของ C1 ตรวจว่า spike มี on interval เพียงหนึ่งแถว fault มี flag และ state reset แล้วเริ่มกลับได้ แยก software bounds จาก actuator limits และ emergency stop

| Profile | peak_H | AUC_H | phi TV | fault_count | สังเกต |
|---|---|---|---|---|---|
| zero | 0.0000 | 0.000 | 0.000 | 0 | H คงที่ที่ baseline 0 ตลอด 30 s |
| one | 1.0000 | 28.750 | 0.200 | 0 | S=1 ตลอด H เข้าใกล้สมดุล ~1 ไม่มี raw>1 (clamp 0%) |
| spike | 0.0400 | 0.050 | 0.016 | 0 | on เพียงหนึ่ง update (input 10.00 → H=0.04 ที่ 10.05) แล้วสลายกลับ |
| fault | 0.9831 | 8.770 | 0.786 | 1 | แถว 15.05: fault=1, H=R=0, phi=0.20, stride=0.055; แถว 15.10 เริ่มสะสมใหม่ H=0.04 |

- fault (input fault) กับ saturation (clamp) เป็นคนละเหตุการณ์: fault รีเซ็ต state เป็น 0 ส่วน clamp แค่จำกัด H ไว้ที่ 1 โดยเก็บ raw ไว้
- software bounds (phi 0.10–0.45 rad, stride 0.040–0.070 m) เป็นแค่ fallback ของซอฟต์แวร์ ไม่แทน actuator limit, joint limit หรือ emergency stop ของหุ่นจริง
- fault ทำให้ phi TV เพิ่มเป็น 0.786 rad (เกือบ 2 เท่าของ step ปกติ) เพราะ reset กระชากคำสั่งลง baseline แล้วไต่ขึ้นใหม่

ทดลองส่ง contract เดิมของ Week03 ถ้ามี แล้วตรวจ phi/stride ที่ R=0 และ R=1 ระบุสิ่งที่ Lab04 ยังไม่ได้ทดสอบ: **R=0 → phi 0.20 rad, stride 0.055 m; R=1 → phi 0.40 rad, stride 0.065 m (ตรงกับ Week03 ที่ m=0/1) Lab04 ยังไม่ได้ทดสอบ: การป้อน phi/stride เข้า CPG จริง, ความถี่/ความเร็วการเดิน, transient ของ gait ขณะ H ค่อยๆ เปลี่ยน, noise ของ sensor stimulus และผลบนหุ่นจริง**

## E. สรุปส่งงาน (10 นาที)

**(1) กลไกและ provenance** — Stimulus S เพิ่ม production P = k_prod·S ส่วน clearance C = k_clear·H_old และ binding B = k_bind·R_old เป็น feedback เชิงลบที่ใช้ state เก่าของรอบเดียวกัน H อินทิเกรตผลสุทธิด้วย Euler (dt = 0.05 s) แล้ว clamp ใน [0,1] receptor normalize H เป็น R ก่อนส่งเข้า bounded mapping ของ Week 03 โครงสร้างอ้างจาก Homchanthanakul et al. (2019) แต่ตัวเลขทั้งหมดเป็น proposed course model ไม่ใช่ค่าจากบทความหรือฮาร์ดแวร์

**(2) prediction ที่ข้อมูลสนับสนุน/ปฏิเสธ** — สนับสนุน: เพิ่ม k_prod (C2) ทำให้ขึ้นเร็วขึ้น (rise 2.70 → 1.05 s); ลด k_clear (C3) ทำให้ฟื้นช้าลง (recovery 2.85 → 5.10 s) และ AUC สูงสุด (11.39); ตัด binding (C4) ทำให้ recovery ยาวขึ้นเป็น 3.80 s; C0 ตอบทันทีภายในหนึ่ง sample (0.05 s) ปฏิเสธ: "peak ของ C2/C3 สูงกว่า C1" ไม่จริง เพราะทุกตัวชน bound ที่ 1.0 (clamp 26–29% ของ updates) และ recovery ของ C2 ไม่ต่างจาก C1 (2.85 s ทั้งคู่) เพราะหลังปิด stimulus อัตราการลดขึ้นกับ k_clear/k_bind ซึ่งเท่ากัน

**(3) ข้อจำกัดและ Week05** — แบบจำลองเป็น deterministic ไม่มี sensor noise, ใช้ stimulus ทรงสี่เหลี่ยมแบบเดียว, timing metric มีความละเอียด 0.05 s และยังไม่ได้เชื่อม CPG จึงยังสรุปเรื่อง gait ไม่ได้ Week05 ต้องป้อน phi/stride จาก R เข้า SO(2) CPG ของ Lab03 แล้ววัด frequency, speed, support legs และ transient ระหว่าง H เปลี่ยน รวมถึงทดสอบ fault ระหว่างเดิน

คำสั่งรันซ้ำ:

```sh
python3 check_submission.py --student-file student_hormone.py
python3 lab04.py --controller-source student --condition all --profile step --output-dir results/comparison
python3 lab04.py --controller-source student --condition C1 --profile zero --output-dir results/zero
python3 lab04.py --controller-source student --condition C1 --profile one --output-dir results/one
python3 lab04.py --controller-source student --condition C1 --profile spike --output-dir results/spike
python3 lab04.py --controller-source student --condition C1 --profile fault --output-dir results/fault
```

Checklist: ■ code ■ comparison CSV 5 files ■ extreme CSV 4 files ■ config ■ plots ■ metrics ■ report (Lab04_Report_TH.docx) ■ คำสั่งรันซ้ำ
