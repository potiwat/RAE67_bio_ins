# Lab 04 — Artificial Hormone Mechanism

## ข้อมูลผู้จัดทำ

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14

## สมการและคำทำนายก่อนทดลอง

ข้อความส่วนนี้บันทึกก่อนรัน comparison และ extreme-input profiles

ใช้ `P=k_prod*S`, `C=k_clear*H_old`, `B=k_bind*R_old` และ `H_new=clamp(H_old+dt(P-C-B),0,1)` โดย receptor มีค่า normalized ในช่วง `[0,1]`

1. C2 มี production สูงกว่า C1 จึงคาดว่า H/R จะเพิ่มเร็วกว่าและมี AUC สูงกว่า แต่อาจเห็น peak เท่ากันเมื่อชน upper clamp
2. C3 มี clearance ต่ำกว่า C1 จึงคาดว่าจะสะสม H มากกว่าและ recovery หลังปิด stimulus ช้ากว่า
3. C4 ตัด binding ออก จึงคาดว่าจะคง H มากกว่า C1 ภายใต้ stimulus เดียวกัน
4. spike หนึ่ง sample (`0.05 s`) ควรทำให้ H เพิ่มเพียงเล็กน้อยและยังอยู่ใน bounds ส่วน fault หนึ่ง sampleควร reset H/R เป็น 0 แล้วเริ่มสะสมใหม่ใน sample ถัดไป

## Block diagram และ state memory

```text
S_k ─────────────► P = k_prod S_k ───────────────┐
                                                  │ (+)
H_old ──────────► C = k_clear H_old ─────────────┤ (−)
  │                                               ▼
  └─► R_old ───► B = k_bind R_old ──(−)──► Euler sum
                                                   │
                                                   ▼
                                             H_raw → clamp
                                                   │
                            ┌── memory next step ───┤
                            ▼                      ▼
                          H_old                  H_new ─► R_new
                                                             │
                                                             ▼
                                          bounded phi / stride mapping
```

Stimulus เปลี่ยน production โดยตรง ส่วน clearance และ binding อ่าน H/R เก่าก่อน update เดียวกัน ผลรวมจึงสร้าง H ใหม่เพียงครั้งเดียว จากนั้น H ใหม่ถูกเก็บเป็น state สำหรับรอบถัดไปและ receptor ใหม่จึงส่งต่อไปยัง mapping. เส้น memory ทำให้ model มีประวัติ แม้ stimulus ปัจจุบันจะเท่ากันก็ตาม

## วิธีทดลองและผล

ตรวจโค้ดด้วยคำสั่งต่อไปนี้ก่อน แล้วจึงรัน profile โดยแยก output directory เพื่อไม่ให้ผลเดิมถูกเขียนทับ

```powershell
py -3 check_submission.py --student-file student_hormone.py
py -3 lab04.py --controller-source student --condition all --profile step --output-dir results\double_comparison
py -3 lab04.py --controller-source student --condition C1 --profile zero --output-dir results\double_zero
py -3 lab04.py --controller-source student --condition C1 --profile one --output-dir results\double_one
py -3 lab04.py --controller-source student --condition C1 --profile spike --output-dir results\double_spike
py -3 lab04.py --controller-source student --condition C1 --profile fault --output-dir results\double_fault
```

checker ผ่าน 13/13 cases และแต่ละ condition มี 601 state rows หรือ 600 updates ผลของ step profile เป็นดังนี้

| Condition | peak H | AUC H (H·s) | latency (s) | rise 10–90% (s) | recovery (s) | upper clamp |
|---|---:|---:|---:|---:|---:|---:|
| C0 | N/A | N/A | 0.05 | 0.00 | 0.05 | N/A |
| C1 | 0.9997 | 9.9996 | 0.15 | 2.70 | 2.85 | 0.0000 |
| C2 | 1.0000 | 10.6724 | 0.10 | 1.05 | 2.85 | 0.2900 |
| C3 | 1.0000 | 11.3891 | 0.15 | 1.45 | 5.10 | 0.2733 |
| C4 | 1.0000 | 10.7547 | 0.15 | 1.70 | 3.80 | 0.2583 |

ความละเอียดของเวลาจาก log คือ `0.05 s` จึงทำให้ C0 ซึ่งตอบสนองตรงมี latency ที่วัดได้ 0.05 s แม้ในแบบจำลอง continuous จะเป็นศูนย์ ส่วน C1 สอง update แรกหลังเปิด stimulus ให้ H เท่ากับ 0.0400 และ 0.0784 ตามลำดับ

ผล extreme profiles ของ C1 สอดคล้องกับขอบเขตที่กำหนด: zero ให้ peak H=0, one ให้ peak H≈1, และ spike หนึ่ง sample ให้ peak H=0.0400 กับ AUC=0.0500 H·s. fault profile พบ fault_count=1 โดยแถวเวลา 15.05 s มี stimulus=NaN, fault=1 และ H=R=0; แถว 15.10 s เริ่มสะสมใหม่เป็น H=R=0.0400

นอกจากนี้รัน C1 step ซ้ำโดยอ่าน `handoff_contract.json` จาก Lab 03 ได้ผลเท่ากับ C1 ปกติ (peak H=0.9997, AUC=9.9996 H·s) แสดงว่า mapping `phi_rad` และ `stride_half_m` รวมถึงค่าคงที่ที่ส่งต่อกันตรงกัน

## อภิปรายผลและข้อจำกัด

ผลสนับสนุนคำทำนายหลัก C2 เพิ่มเร็วกว่า C1 และมี AUC สูงกว่า แต่ peak ต่างกันน้อยเพราะชนขอบบน จึงไม่ควรใช้ peak เพียงตัวเดียวตัดสินผลของ production. C3 มี AUC สูงสุดและ recovery 5.10 s ซึ่งช้ากว่า C1 ชัดเจนตามผลของ clearance ที่ลดลง ส่วน C4 ไม่มี binding จึงมี AUC และ recovery สูงกว่า C1

upper-clamp fraction ช่วยแยก C2–C4 ที่มี peak เท่ากับ 1 ได้ และ raw CSV แยก clamp event ออกจาก input fault อย่างชัดเจน การคำนวณนี้เป็น deterministic proposed course model; ยังไม่มี sensor noise, ความคลาดเคลื่อนของ actuator หรือ body dynamics ดังนั้น fault reset เป็นเพียง software fallback ไม่ใช่การรับรองความปลอดภัยของฮาร์ดแวร์จริง
