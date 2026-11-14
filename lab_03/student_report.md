# Lab 03 — SO(2) CPG และ Alternating Tripod

## ข้อมูลผู้จัดทำ

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14

## คำทำนายก่อนทดลอง

ข้อความส่วนนี้บันทึกก่อนรัน gait comparison และ Week 4 bridge

1. condition `fast` เพิ่ม `phi` จาก 0.20 เป็น 0.40 rad/step โดยคง `alpha=1.10` จึงคาดว่าความถี่ oscillator และความเร็วใน kinematic model จะเพิ่มขึ้น
2. condition `high_gain` เพิ่ม `alpha` จาก 1.10 เป็น 1.30 โดยคง `phi=0.20` จึงคาดว่าจะเปลี่ยน amplitude และ foot clearance จาก nonlinearity ของ `tanh` และอาจทำให้ความถี่ที่วัดได้เปลี่ยนเล็กน้อย
3. ขา LF/RM/LH และ RF/LM/RH ควรสลับ swing/stance คนละเฟสตลอดทุก condition เพราะ decoder ใช้ phase sign ตรงข้ามกัน

## ตัวแปรควบคุม

ทุก condition ใช้ `dt=0.05 s`, duration 30 s, warmup 10 s, initial oscillator state, stride และ lift height ชุดเดียวกัน เปลี่ยนทีละตัวระหว่าง `phi` และ `alpha`

## วิธีทดลองและผล

`student_cpg.py` ผ่าน checker 5/5 และ boundary `o2=0` ให้ lift เป็น 0 พร้อม contact ทุกขา จากนั้นรัน:

```powershell
py -3 cpg_walk_sim.py --condition baseline --duration 2 --output-dir results\double_smoke
py -3 cpg_walk_sim.py --condition all --output-dir results\double_gait
py -3 week4_bridge.py --output-dir results\double_week4_bridge
```

ผล gait comparison 30 s:

| Condition | alpha | phi (rad/step) | frequency (Hz) | speed (m/s) | max clearance (m) | LF duty factor |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1.10 | 0.20 | 0.625 | 0.0778 | 0.01710 | 0.494 |
| fast | 1.10 | 0.40 | 1.267 | 0.1555 | 0.01711 | 0.501 |
| high_gain | 1.30 | 0.20 | 0.544 | 0.0945 | 0.02464 | 0.494 |

ทุก condition มี support legs ต่ำสุดและสูงสุดเท่ากับ 3 ตาม alternating-tripod decoder ผล Week 4 bridge แบ่งช่วง `m=0,1,0` ได้ความถี่ `0.625, 1.263, 0.625 Hz` และความเร็ว `0.0776, 0.1833, 0.0774 m/s` พร้อมสร้าง `results/double_week4_bridge/handoff_contract.json`

## อภิปรายผลและข้อจำกัด

ผลสนับสนุนคำทำนายของ `fast`: การเพิ่ม `phi` สองเท่าทำให้ความถี่เพิ่มจาก 0.625 เป็น 1.267 Hz และความเร็วเพิ่มใกล้สองเท่า โดย clearance แทบไม่เปลี่ยน ส่วน `high_gain` เพิ่ม clearance จากประมาณ 0.0171 เป็น 0.0246 m และเพิ่มความเร็ว แต่ความถี่ลดเป็น 0.544 Hz แสดงว่า gain และ nonlinearity ไม่ได้เปลี่ยนทุก metric ไปในทิศทางเดียวกัน

Week 4 bridge กลับสู่ค่าความถี่และความเร็วใกล้ baseline เมื่อ `m` กลับเป็น 0 จึงสอดคล้องกับ bounded mapping ที่ไม่มี memory ในตัวมันเอง การมี support legs 3 ขาเป็นเพียง state จาก decoder ไม่ได้พิสูจน์ static/dynamic stability เพราะแบบจำลองไม่มีแรงสัมผัส, rigid-body dynamics, CoM หรือ support polygon ผลทั้งหมดจึงเป็น kinematic teaching model ไม่ใช่สมรรถนะหุ่นยนต์จริง
