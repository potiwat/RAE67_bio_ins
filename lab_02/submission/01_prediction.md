# Lab 02 — สมมติฐานก่อนทดลอง (รอบทำใหม่)

บันทึกเมื่อ: **2026-11-11 22:11 (UTC+7)** ก่อนเติม TODO ใน `student_controller.py` (ไฟล์ถูกคืนเป็น starter ของผู้สอนแล้ว) และก่อนรัน `lab02.py` ทุกโหมดในรอบนี้

**การเปิดเผยข้อมูล:** รอบนี้เป็นการทำ Lab02 ใหม่ตั้งแต่ศูนย์ ผู้เขียนเคยเห็นค่าเฉลี่ยของขั้น A จากรอบก่อนแล้ว (C1 extra switches ≈ 12.4, C1 false trigger ≈ 8.4 /min, latency enter: C1 ≈ 0.02 s, C2 ≈ 0.41 s, C3 ≈ 0.04 s) ดังนั้น prediction ของค่าเหล่านี้**ไม่ใช่ prediction แบบ blind** ค่าที่ไม่เคยเห็นและใช้ทดสอบจริงในรอบนี้คือ ข้อ 1 (σ = 0 และ 0.03 m ของ C1), ข้อ 2 (C2 ที่ σ = 0.03 m) และข้อ 3 (delay 100/300 ms) รวมถึงข้อ 4 (C3 กับ command limit) ซึ่งคำนวณจากสมการเท่านั้น

ข้อมูลที่ใช้คาด: `LabConfig` (dt = 0.02 s, T = 0.35 m, T_enter/T_exit = 0.32/0.38 m, β = 0.25, Kp = 2.0, clamp ±0.6) และ trajectory ใน `true_distance_m()` (ช่วงเข้า/ออกเร็ว 0.0875 m/s = 0.00175 m ต่อ sample; ข้าม 0.35 m ที่ t ≈ 6.857 s และ 13.143 s; ช่วง 8–12 s อยู่ที่ 0.25 ± 0.015 m)

## ข้อ 1 — เมื่อ noise เพิ่ม C1 จะมี switching count เปลี่ยนอย่างไร

**คาด:** extra switches ของ C1 เพิ่มเกือบเป็นสัดส่วนกับ σ เพราะ C1 เทียบ raw distance กับ T โดยตรง ช่วงที่ raw ข้าม T กลับไปกลับมากว้างประมาณ ±2σ / 0.0875 m/s รอบแต่ละ crossing

| σ (m), delay 0 | extra switches ต่อ trial (คาด) | false trigger (คาด, /min) |
|---|---|---|
| 0.00 | 0 พอดี (switching = 2) | 0 |
| 0.01 | ≈ 12 (เคยเห็น) | ≈ 8 (เคยเห็น) |
| 0.03 | ≈ 35–40 | ≈ 22–28 |

ที่ σ = 0.03 m ช่วงค้างใกล้ 8–12 s อยู่ห่าง T 2.8–3.8σ อาจมี raw เกิน T บ้างแต่ไม่เกิน 1 ครั้งต่อ trial โดยเฉลี่ย delay ไม่ควรเปลี่ยน switching count (แค่เลื่อนเวลา) — ทดสอบด้วยการรัน C1 robustness-full เพิ่ม

## ข้อ 2 — C2 จะลด false trigger โดยแลกกับ latency หรือ recovery time อย่างไร

**คาด:** C2 มี false trigger = 0 และ extra switches = 0 ทั้งที่ σ = 0.01 และ 0.03 m แลกกับ latency enter/exit ≈ 0.40 s (hysteresis 0.03 m / 0.0875 m/s = 0.34 s + EMA lag (1−β)/β·dt = 0.06 s) recovery time ≈ latency เพราะไม่มี chatter

เหตุผลที่ไม่ chatter แม้ σ = 0.03: EMA ลด SD เหลือ σ·√(β/(2−β)) ≈ 0.38σ = 0.011 m ส่วน band ระหว่าง T_enter กับ T_exit กว้าง 0.06 m ≈ 5.3 SD ของ filtered

ที่ σ = 0.03 m: mean latency ใกล้เดิม (0.35–0.42 s) แต่ SD เพิ่มเป็นประมาณ 0.1 s (0.011 m / 0.0875 m/s ≈ 0.13 s)

## ข้อ 3 — เมื่อเพิ่ม sensor delay การตอบสนองจะเลื่อนอย่างไร

**คาด:** latency เพิ่มแบบบวกเท่ากับ delay: C2 ≈ 0.40 + 0.10 = 0.50 s (100 ms) และ ≈ 0.70 s (300 ms) ส่วน C1 (รันเพิ่ม) ≈ 0.25–0.30 s ที่ 300 ms (noise ทำให้บาง trial เปลี่ยนก่อนเวลาได้เล็กน้อย)

ผลข้างเคียง: delay 100/300 ms = 5/15 sample แรกของทุก trial ไม่มีค่า (`MISSING_OR_DELAY_BUFFER`) → invalid samples 5 และ 15 ต่อ trial, command = safe 0, state ค้าง FAR ไม่มี trial ใดต้อง exclude เพราะช่วงนั้นอยู่ก่อน crossing มาก (0–0.3 s)

## ข้อ 4 — C3 ชน command limit ช่วงใด

**คาด:** C3 **ไม่ชน** limit ±0.6 เลยใน protocol นี้ เพราะ u = 2(0.35 − d̂): ที่ 0.60 m ได้ −0.50 และที่ 0.25 m ได้ +0.20 ต้องมี d̂ > 0.65 m หรือ < 0.05 m จึงจะ clamp ซึ่ง trajectory ไม่ถึง (noise ของ filtered ≈ 0.004 m ที่ σ = 0.01) Mean |Δu| ของ C3 ≈ 0.004–0.005 (มาจาก noise ของ filtered มากกว่าจาก ramp 0.0035 ต่อ sample)

## ข้อ 5 — C0

**คาด:** C0 เปลี่ยน state ตามเวลา (NEAR 4–16 s) จึง latency enter ≈ 0.003 s (sample แรกหลัง 6.857 s) แต่ latency exit ≈ 2.86 s, false trigger = 1 ครั้งต่อ trial ≈ 3.0 /min (NEAR ตั้งแต่ 4 s ก่อน crossing) และ Mean |Δu| = 2 × 0.6 / 1000 = 0.0012

## บันทึกการแก้สมมติฐาน

ยังไม่มีการแก้ หากมีการแก้หลังเห็นผล จะเพิ่มบรรทัดที่นี่พร้อมวันเวลาและเหตุผล โดยไม่ลบข้อความด้านบน
