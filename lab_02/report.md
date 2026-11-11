## การคาดเดาผลก่อนทำแลป

คำตอบต่อไปนี้เป็นการคาดการณ์จากหลักการและโครงสร้าง controller ก่อนรันการทดลอง ไม่ใช่ผลที่วัดได้จริง

### 1. เมื่อ noise เพิ่มขึ้น C1 จะมี switching count เปลี่ยนอย่างไร

คาดว่า switching count ของ C1 จะเพิ่มขึ้น โดยเฉพาะช่วงที่ระยะอยู่ใกล้ threshold 0.35 m เพราะ C1 ตัดสินจากระยะดิบเพียงด้านเดียว: ต่ำกว่า threshold เป็น NEAR และตั้งแต่ threshold ขึ้นไปเป็น FAR เมื่อ noise ทำให้ค่าที่อ่านแกว่งข้าม threshold ไปมา สถานะจึงอาจสลับหลายครั้ง แม้ระยะจริงแทบไม่เปลี่ยน ช่วงค้างใกล้ที่มี disturbance มีโอกาสเห็นอาการนี้ชัดกว่าช่วงที่อยู่ไกลจาก threshold

### 2. C2 จะลด false trigger โดยแลกกับ latency หรือ recovery time อย่างไร

คาดว่า C2 จะมี false trigger และการสลับสถานะจาก noise น้อยกว่า C1 เพราะ low-pass filter ใช้ข้อมูลปัจจุบันเพียงบางส่วน (`beta = 0.25`) และ hysteresis แยกเกณฑ์เข้า NEAR ที่ 0.32 m ออกจากเกณฑ์กลับ FAR ที่ 0.38 m ทำให้การแกว่งในช่วงระหว่างสองเกณฑ์ไม่ทำให้สถานะสลับทันที อย่างไรก็ตาม การกรองทำให้ค่าที่ใช้ตัดสินตอบสนองช้ากว่าค่าดิบ อีกทั้งเกณฑ์เข้าและออกต่างจาก 0.35 m จึงคาดว่า latency หรือ recovery time อาจยาวขึ้น โดยเฉพาะเมื่อระยะค่อย ๆ เคลื่อนผ่านเกณฑ์ คาดการณ์นี้เป็น trade-off ไม่ได้หมายความว่า C2 จะช้ากว่าในทุก trial

### 3. เมื่อเพิ่ม sensor delay 300 ms เส้น command จะเลื่อนจาก physical event เท่าใด

คาดว่า command ที่อาศัย sensor ใน C1–C3 จะตอบสนองช้าลงใกล้เคียง 300 ms เมื่อเทียบกับกรณีไม่มี delay เพราะ controller ได้รับข้อมูลระยะจากเวลาก่อนหน้า อย่างไรก็ดี การเลื่อนที่วัดได้อาจไม่เท่ากับ 300 ms พอดี เนื่องจากการสุ่มตัวอย่างเป็นช่วง ๆ, noise, การกรองและ hysteresis ของ C2 และการนิยามเวลาตอบสนองจากการข้าม threshold; ควรตรวจเทียบ physical crossing กับ first correct response ในกราฟและ metric จริง ส่วน C0 เป็น open-loop sequence ที่ไม่ใช้ sensor จึงคาดว่า sensor delay จะไม่เลื่อน command ของ C0

## บทนำ

Lab 02 เปรียบเทียบ controller สี่แบบใน simulator ด้วยระยะอ้างอิงเดียวกัน เพื่อศึกษาผลของ sensor uncertainty ต่อการตอบสนอง การสลับสถานะ และ command โดยค่าทั้งหมดเป็น proposed course model ไม่ใช่การทดสอบหรือรับรองฮาร์ดแวร์จริง

## วัตถุประสงค์

- เปรียบเทียบ C0 open-loop, C1 single threshold, C2 low-pass filter ร่วมกับ hysteresis และ C3 proportional controller ที่มี clamp
- วัด latency, false trigger, switching/recovery, ความเปลี่ยนแปลง command และผลของ noise/delay
- เติมและตรวจ student controller พร้อมเก็บ configuration และ raw trial เพื่อทำซ้ำได้

## วิธีการ

เติม `student_controller.py` ตาม recurrence ของ low-pass filter, threshold 0.35 m, hysteresis 0.32/0.38 m และ proportional command `Kp(target − distance)` ที่ clamp อยู่ในช่วง [-0.6, 0.6] จากนั้นรัน test suite, grader และ student comparison; รัน reference comparison แยกไว้ตรวจเทียบด้วย

```text
ระยะจริงจำลอง → sensor (Gaussian noise / sample delay) → controller C0–C3
      ↑                                                       ↓
      └────────────── trajectory / feedback ใน simulator ← command
```

trajectory ยาว 20 s, sample interval 0.02 s, threshold 0.35 m; student comparison ใช้ noise σ=0.01 m, delay 0 ms และ 5 trials ต่อ condition (C0–C3); รัน reference comparison แยกเพื่อเทียบด้วย ส่วน robustness ของ C2 ใช้ reference controller ตาม `run_config.json` ทั้งชุดย่อ 5 combinations × 3 trials และชุดเต็ม 3 noise levels × 3 delays × 5 trials. เพิ่ม C1 ชุดเต็ม 45 trials ด้วย reference controller เพื่อทดสอบ prediction เรื่อง noise ของ C1 โดยตรง grader ยืนยันว่า student controller ตรงกับ reference ใน C0–C3 ที่ noise σ=0.01 m และ delay 0 ms; ไม่อ้างว่าชุด robustness เป็น student-source run ค่าในตารางเป็น mean ± SD ระหว่าง trials

การตรวจโค้ด: `python -m unittest discover -s tests -v` ผ่าน 12 tests; `grade_submission.py` ผ่าน 10/10 checks รวมการเปรียบเทียบ trace C0–C3 กับ reference

## ผลการทดลอง

### C0–C3 ที่ noise σ=0.01 m, delay=0 ms (n=5 ต่อ condition)

| Condition | Latency เข้า NEAR (s) | Latency ออก NEAR (s) | False trigger (ครั้ง/นาที) | Extra switches (ครั้ง) | Mean \|Δcommand\| ต่อ sample |
|---|---:|---:|---:|---:|---:|
| C0 | 0.003 ± 0.000 | 2.857 ± 0.000 | 2.997 ± 0.000 | 0.000 ± 0.000 | 0.0012 ± 0.0000 |
| C1 | 0.019 ± 0.026 | 0.029 ± 0.011 | 8.392 ± 5.765 | 12.400 ± 2.608 | 0.0086 ± 0.0020 |
| C2 | 0.407 ± 0.043 | 0.453 ± 0.036 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.0012 ± 0.0000 |
| C3 | 0.043 ± 0.024 | 0.089 ± 0.041 | 1.798 ± 1.642 | 1.600 ± 0.894 | 0.0046 ± 0.0000 |

### ผลของ noise ต่อ C1 และ C2 ที่ delay=0 ms (ชุดเต็ม, n=5)

| σ (m) | C1 extra switches (ครั้ง) | C1 false trigger (ครั้ง/นาที) | C2 extra switches (ครั้ง) | C2 false trigger (ครั้ง/นาที) |
|---:|---:|---:|---:|---:|
| 0.00 | 0.0 | 0.000 | 0.0 | 0.000 |
| 0.01 | 12.0 | 12.587 | 0.0 | 0.000 |
| 0.03 | 39.2 | 32.368 | 0.0 | 0.000 |

### ผลของ delay ต่อ C2 ที่ σ=0.01 m (ชุดเต็ม, n=5)

| Delay (ms) | Latency เข้า (s) | Latency ออก (s) | Recovery (s) | Invalid samples เฉลี่ย/ trial |
|---:|---:|---:|---:|---:|
| 0 | 0.431 | 0.417 | 0.434 | 0 |
| 100 | 0.487 | 0.537 | 0.543 | 5 |
| 300 | 0.703 | 0.713 | 0.753 | 15 |

กราฟตัวแทนจาก raw CSV:

[กราฟ C1: σ=0.01 m, delay 0 ms](results/lab02_complete_20261111/graphs/student_C1.png) · [กราฟ C2: σ=0.01 m, delay 0 ms](results/lab02_complete_20261111/graphs/student_C2.png) · [กราฟ C1: σ=0.03 m](results/lab02_complete_20261111/graphs/student_C1_noise003.png) · [กราฟ C2: σ=0.03 m, delay 300 ms](results/lab02_complete_20261111/graphs/student_C2_noise003_delay300.png)

## อภิปราย

1. **C1 เมื่อ noise เพิ่ม:** ตรงกับ prediction อย่างชัดเจนในชุดเต็ม: C1 extra switches เพิ่มจาก 0 ที่ σ=0 เป็น 12.0 ที่ σ=0.01 และ 39.2 ที่ σ=0.03; false-trigger rate เพิ่มจาก 0 เป็น 12.587 และ 32.368 ครั้ง/นาทีตามลำดับ การใช้ raw distance กับ threshold เดียวทำให้ noise ที่พาค่าข้าม 0.35 m สร้างการสลับสถานะได้
2. **C2 กับ trade-off:** ผลตรงกับ prediction ด้านลด false trigger/chatter และแลกกับการตอบสนองช้า เมื่อเทียบ C1 ที่ σ=0.01: C2 มี extra switches 0 เทียบกับ 12.4 และ false trigger 0 เทียบกับ 8.392 ครั้ง/นาที แต่ latency เข้า/ออกเฉลี่ย 0.407/0.453 s เทียบกับ 0.019/0.029 s ของ C1; recovery 0.454 s เทียบกับ 0.181 s การกรองและเกณฑ์ hysteresis ที่ต่างกันทำให้ต้องรอค่าผ่านเงื่อนไขก่อนเปลี่ยน state ในชุด C2 ค่า noise 0.03 ไม่เพิ่ม extra switch หรือ false trigger เมื่อเทียบกับ noise 0/0.01 แต่ latency ไม่ได้เพิ่มตาม noise แบบ monotonic จึงไม่ควรสรุปว่า filter กำจัดผล noise ทุกชนิด
3. **Delay 300 ms:** C2 ที่ σ=0.01 มี latency เข้าเพิ่ม 0.272 s และ latency ออกเพิ่ม 0.296 s จาก delay 0 เป็น 300 ms จึงใกล้ 300 ms ตามคาด; recovery เพิ่ม 0.319 s ในทางกลับกัน C1 ที่มี noise σ=0.01 เพิ่ม latency เข้า/ออกเพียง 0.168/0.184 s ซึ่งไม่เท่ากับ delay โดยตรง เนื่องจากเกณฑ์ข้าม, noise และการสลับสถานะมีผลร่วมด้วย ชุด delay ยังเริ่มด้วย sample ที่ไม่มีใน buffer: ที่ 100/300 ms พบ invalid 5/15 samples ต่อ trial จึงต้องแยก startup missing เหล่านี้จาก noise
4. **C0 และ metric:** C0 เป็น open-loop จึงไม่ใช้ sensor และคำสั่งถูกกำหนดตามเวลา อย่างไรก็ตาม latency เข้า NEAR ที่คำนวณได้เกือบศูนย์เพราะ C0 เข้าสถานะก่อนระยะจริงข้าม threshold; จึงไม่ใช่หลักฐานว่า sensorimotor response เร็ว ส่วน false trigger และ latency ออกสะท้อนข้อจำกัดของ schedule นี้ การตีความ C0 ด้วย metric latency แบบเดียวกับ controller ที่ใช้ sensor ต้องระวัง

## สรุป

ใน simulator ชุดนี้ C1 ตอบสนองเร็วแต่ไวต่อ noise และเกิดการสลับ/false trigger มากกว่า C2; C2 ลดการสลับได้แต่มี latency และ recovery ยาวขึ้น ส่วน delay มีแนวโน้มเพิ่ม latency ใกล้ค่าที่ใส่ โดยผลจริงขึ้นกับ controller และ metric. ผลทั้งหมดเป็น repeated synthetic trials บน trajectory เดียว ไม่ใช่การวัด sensor, actuator หรือหุ่นยนต์จริง; command, threshold และ limit ต้องตรวจสอบและสอบเทียบใหม่ก่อนใช้กับฮาร์ดแวร์

ผล CSV, config, grader, กราฟ และภาพหน้าจออยู่ใน [results/lab02_complete_20261111](results/lab02_complete_20261111): [screenshot C1](results/lab02_complete_20261111/screenshots/student_C1_screenshot.png), [screenshot C2](results/lab02_complete_20261111/screenshots/student_C2_screenshot.png), [screenshot C1 noise สูง](results/lab02_complete_20261111/screenshots/student_C1_noise003_screenshot.png) และ [screenshot C2 noise/delay สูง](results/lab02_complete_20261111/screenshots/student_C2_noise003_delay300_screenshot.png) ภาพกราฟแสดง physical threshold crossing และ first correct response ที่คำนวณจาก trial CSV
