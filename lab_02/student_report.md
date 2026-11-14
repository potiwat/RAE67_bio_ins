# Lab 02 — Robust Reactive Lamp

## ข้อมูลผู้จัดทำ

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14

## คำทำนายก่อนทดลอง

ข้อความส่วนนี้บันทึกก่อนรันการทดลองที่สร้างผล C0–C3 และ robustness

1. เมื่อ noise เพิ่มขึ้น C1 ซึ่งใช้ threshold เดียวกับข้อมูลดิบจะมีจำนวนการสลับสถานะและ false trigger เพิ่มขึ้น เพราะค่าที่แกว่งใกล้ 0.35 m สามารถข้าม threshold ไปมาได้
2. C2 น่าจะลด false trigger และการสลับสถานะเมื่อเทียบกับ C1 เพราะมี low-pass filter และ hysteresis แต่ต้องแลกกับ latency ตอนเข้าและออกจากสถานะ เนื่องจากค่ากรองเปลี่ยนช้ากว่าค่าดิบและต้องข้าม threshold คนละค่า
3. เมื่อ sensor delay เพิ่มเป็น 300 ms เส้น state/command น่าจะเลื่อนช้ากว่าเหตุการณ์ทางกายภาพประมาณระดับเดียวกับ delay โดยอาจมีผลจาก sampling และ filter เพิ่มเติม

## วิธีทดลอง

ใช้ controller ใน `student_controller.py` ผ่าน checker 10 รายการและ unit tests จากนั้นรันสาม protocol โดยไม่เขียนทับผลเดิม:

```powershell
py -3 lab02.py --controller-source student --protocol controller-comparison --student-file student_controller.py --out results\double_comparison
py -3 lab02.py --controller-source student --protocol robustness-short --condition C2 --student-file student_controller.py --out results\double_c2_short
py -3 lab02.py --controller-source student --protocol robustness-full --condition C2 --student-file student_controller.py --out results\double_c2_full
```

comparison ใช้ 5 trials ต่อ condition, `dt=0.02 s`, noise `0.01 m`, delay `0 ms` และ seed base `202602` ไฟล์ controller ที่ใช้มี SHA-256 `a9a24b1272385a7494b624933991e45078eac8e97550da693c8e57f0b7d59bbd`

## ผลการทดลอง

ผลเฉลี่ยจาก comparison:

| Condition | extra switches | false trigger rate (ครั้ง/min) | enter latency (s) | exit latency (s) | recovery (s) |
|---|---:|---:|---:|---:|---:|
| C0 | 0.0 | 2.997 | 0.003 | 2.857 | 2.857 |
| C1 | 12.4 | 8.392 | 0.019 | 0.029 | 0.181 |
| C2 | 0.0 | 0.000 | 0.407 | 0.453 | 0.454 |
| C3 | 1.6 | 1.798 | 0.043 | 0.089 | 0.109 |

ผล C2 แบบ full robustness ที่ไม่มี noise แสดง enter latency เพิ่มจาก `0.423 s` ที่ delay 0 ms เป็น `0.523 s` ที่ 100 ms และ `0.723 s` ที่ 300 ms ส่วนทุกชุด C2 มี extra switches และ false trigger rate เท่ากับ 0 ในการรันนี้ เมื่อมี noise ผล latency แกว่งตาม seed แต่ชุด delay 300 ms ยังช้ากว่าชุด delay 0 ms โดยรวม

## อภิปรายผลและข้อจำกัด

ผลสนับสนุนคำทำนายว่า C1 ไวต่อ noise มากกว่า C2: C1 มี extra switches เฉลี่ย 12.4 และ false trigger 8.392 ครั้ง/min ขณะที่ C2 เป็น 0 ทั้งสอง metric แต่ C2 มี enter/exit latency สูงกว่า C1 ประมาณ 0.39–0.42 s เพราะ filter และ hysteresis การเพิ่ม delay จาก 0 เป็น 300 ms ในกรณีไม่มี noise เพิ่ม enter latency ของ C2 เท่ากับ 0.300 s จึงสอดคล้องกับคำทำนายโดยตรง

ผล C0 ไม่ควรใช้ตัดสินคุณภาพ sensor feedback เพราะเป็น open-loop sequence และนิยาม false trigger/recovery อิง physical threshold จึงทำให้ค่าบางตัวดูสูงแม้ไม่มี extra switch ข้อจำกัดหลักคือข้อมูลทั้งหมดมาจาก deterministic simulator และ proposed course model การที่ C2 ไม่มี false trigger ใน protocol นี้ไม่ได้รับรองว่าจะปลอดภัยหรือเสถียรกับ sensor และหุ่นยนต์จริง
