# Lab 03 — สมมติฐานก่อนทดลอง

บันทึกเมื่อ: 2026-11-11 19:13 (UTC+7) ก่อนเติม `student_cpg.py` และก่อนรัน `cpg_walk_sim.py` / `week4_bridge.py` ใด ๆ (ยังไม่ได้เปิดไฟล์ใน `results/smoke_test/` ที่มีอยู่แล้วใน repo)
สิ่งที่ใช้ประกอบการคาด: สมการใน README ข้อ 5, ค่าคงที่ในโค้ด (dt = 0.05 s, stride_half = 0.055 m, lift_height = 0.030 m, initial condition o₁ = 0.10, o₂ = 0.00, warmup 10 s, duration 30 s) และกฎ decoder `x_rel = stride·sign·o₁`, `lift = lift_height·max(0, sign·o₂)`, `contact = sign·o₂ ≤ 0`

## แบบจำลองที่ใช้คาด

- SO(2) map คือการหมุนเวกเตอร์ (o₁, o₂) ไปมุม φ ต่อ step คูณด้วย α แล้วผ่าน tanh ถ้า amplitude ไม่ใหญ่มาก มุมต่อ step ≈ φ ดังนั้นคาบ ≈ 2π/φ step
  - φ = 0.20 → 31.4 step × 0.05 s = 1.57 s → **f ≈ 0.64 Hz**
  - φ = 0.40 → 15.7 step × 0.05 s = 0.785 s → **f ≈ 1.27 Hz**
- amplitude: ใช้ describing function ของ tanh (N(X) ≈ 1 − X²/4) ต้องได้ α·N(αr) = 1 → (αr)² = 4(1 − 1/α)
  - α = 1.10 → r ≈ 0.55
  - α = 1.30 → r ≈ 0.74 (การประมาณหยาบลงเมื่อ αr ใกล้ 1 ค่าจริงอาจต่ำกว่านี้เล็กน้อย)
- body ก้าวหน้า 2·r·stride_half ต่อครึ่งรอบ (ขาที่อยู่ใน stance กวาด x_rel จาก +r·s ไป −r·s) → 4·r·stride_half ต่อรอบ → **speed ≈ 4·r·stride_half·f**

## ข้อ 1 — เพิ่ม φ จาก 0.20 เป็น 0.40 rad ความถี่ที่วัดได้จะเปลี่ยนอย่างไร

**คาด:** ความถี่เพิ่มเกือบเป็นสองเท่า จาก ≈ 0.64 Hz เป็น ≈ 1.27 Hz (อาจคลาดไม่กี่ % เพราะ tanh และเพราะคาบนับเป็นจำนวน step เต็ม) เพราะ φ คือมุมที่เวกเตอร์ (o₁, o₂) หมุนต่อหนึ่ง time step

speed คาดเพิ่มเป็นประมาณสองเท่าด้วย (≈ 0.077 → ≈ 0.15 m/s) เพราะระยะต่อรอบเท่าเดิม แต่รอบเร็วขึ้น ส่วน clearance ไม่ควรเปลี่ยนมาก (amplitude ขึ้นกับ α เป็นหลัก)

## ข้อ 2 — เพิ่ม α จาก 1.10 เป็น 1.30 แอมพลิจูดและ foot clearance จะเปลี่ยนอย่างไร

**คาด:** amplitude ของ o₁, o₂ เพิ่มจาก ≈ 0.55 เป็น ≈ 0.7 กว่า ๆ ดังนั้น clearance (= 0.030·max o₂) เพิ่มจาก ≈ 16 mm เป็น ≈ 21–22 mm และ speed เพิ่มตาม amplitude (≈ 0.077 → ≈ 0.10 m/s) ส่วนความถี่ควรเปลี่ยนน้อย (< 10 %) เพราะ φ เท่าเดิม แต่ waveform จะเหลี่ยมขึ้นเล็กน้อยจาก tanh ที่อิ่มตัวมากขึ้น

## ข้อ 3 — ขา Tripod A และ Tripod B ควรมี phase relation เท่าใด

**คาด:** ต่างเฟสกัน π rad (180°, antiphase) เพราะ Tripod B ใช้ sign = −1 คูณ o₁ และ o₂ ตรง ๆ จึงเป็นสัญญาณกลับขั้วของ Tripod A ทุกขณะ ผลคือ contact ของสอง tripod สลับกันพอดี
- duty factor ของ LF ≈ 0.50
- minimum support legs = 3 และ maximum = 3 (จะเป็น 6 เฉพาะ sample ที่ o₂ = 0 พอดี ซึ่งไม่น่าเกิดหลัง warmup) ดังนั้นไม่มีช่วงที่ support ต่ำกว่า 3

## ข้อ 4 — metric ใดที่ kinematic simulator ยังวัดไม่ได้

dynamic stability (ZMP / support polygon margin ที่มี CoM จริง), contact force และ friction / slip, motor torque และ power / energy (cost of transport), actuator tracking error, ผลของ inertia และความยืดหยุ่นของขา รวมถึงพื้นไม่เรียบ เพราะ simulator คำนวณเฉพาะตำแหน่งเท้าจาก decoder และให้ body x เป็นค่าเฉลี่ยของ stance constraint ไม่มีมวลหรือแรง

## ข้อ 5 — Week 4 bridge (m = 0 → 1 → 0)

- m = 1: φ_cmd = 0.40 rad, stride_cmd = 0.065 m (ไม่ชน bounds) → f ≈ 1.27 Hz, speed ≈ 4·0.55·0.065·1.27 ≈ 0.18 m/s
- m = 0 ช่วงแรกและช่วงท้าย: ค่าใกล้ baseline (≈ 0.64 Hz, ≈ 0.077 m/s)
- เมื่อ m กลับจาก 1 เป็น 0: คาดว่า frequency เปลี่ยนเกือบทันทีภายในหนึ่งรอบ เพราะ m เปลี่ยนแบบ step และ φ ไม่มี dynamics ของตัวเอง amplitude แทบไม่ต้องปรับเพราะ α คงที่ จึงมี transient เล็กน้อยเท่านั้น
- ผลข้างเคียงที่คาด: ตอน stride เปลี่ยนแบบ step ที่ t = 10 s และ 20 s ค่า x_rel ของขาที่อยู่ใน stance จะกระโดด ทำให้ body_x มีจุดกระโดดเล็ก ๆ (สูงสุดประมาณ 0.010·|o₁| ≈ 5 mm) ซึ่งเป็น artifact ของ kinematic model

## บันทึกการแก้สมมติฐาน

(ยังไม่มี — ถ้ามีการแก้หลังเห็นผลจะบันทึกเวลาและเหตุผลไว้ที่นี่ โดยไม่ลบข้อความเดิม)
