# รายงาน Lab 02: Robust Reactive Lamp

**ชื่อ/รหัสนักศึกษา:** ____________________  
**กลุ่ม:** ____________________  
**วันที่:** ____________________

## วัตถุประสงค์และวิธีทดลอง

เปรียบเทียบ controller C0–C3 ใน simulator ที่ใช้ระยะจริงจำลองชุดเดียวกัน โดยประเมิน latency, recovery time, false trigger, จำนวนการสลับสถานะ และการเปลี่ยน command จากนั้นทดสอบ C2 ที่ noise 3 ระดับ (`sigma = 0.00, 0.01, 0.03 m`) และ sensor delay 3 ระดับ (`0, 100, 300 ms`) ใช้ 5 trials ต่อชุด รวม 45 trials สำหรับ robustness และ 20 trials สำหรับ controller comparison (`sigma = 0.01 m`, delay `0 ms`).

ตรวจโค้ดด้วย unit/integration tests ผ่าน `12/12` tests และ grader ผ่าน `10/10` checks รวมการทดลองครบ C0–C3.

การคาดการณ์ก่อนทดลองไม่ได้ถูกบันทึกไว้ก่อนรัน จึงไม่นำมาเขียนย้อนหลังเป็น prediction ก่อนทดลอง

### แผนภาพการไหลของข้อมูล

```text
trajectory ระยะจริง ──> sensor simulator (noise + delay) ──> controller C0–C3 ──> command
        │                                                                   
        └──────────────────> ground truth สำหรับคำนวณ metric
```

การทดลองนี้เป็นการเปรียบเทียบ controller ใน simulator โดย command **ไม่ได้ป้อนกลับไปเปลี่ยน trajectory**; ground truth ใช้สำหรับประเมินผลเท่านั้น

## ผลการเปรียบเทียบ controller

ค่าในตารางเป็นค่าเฉลี่ยจาก 5 trials ต่อ condition:

| Controller | Enter latency (s) | Exit latency (s) | Recovery (s) | False trigger (/min) | Extra switches | Mean \|Δcommand\| |
|---|---:|---:|---:|---:|---:|---:|
| C0 open-loop | 0.003 | 2.857 | 2.857 | 3.00 | 0.0 | 0.00120 |
| C1 single threshold | 0.019 | 0.029 | 0.181 | 8.39 | 12.4 | 0.00864 |
| C2 filter + hysteresis | 0.407 | 0.453 | 0.454 | 0.00 | 0.0 | 0.00120 |
| C3 proportional + clamp | 0.043 | 0.089 | 0.109 | 1.80 | 1.6 | 0.00465 |

C1 ตอบสนองเร็วกว่า C2: enter latency เฉลี่ยต่ำกว่า `0.388 s` และ exit latency ต่ำกว่า `0.424 s` แต่มี extra switches เฉลี่ย `12.4` ครั้งและ false trigger `8.39/min`; C2 ไม่มี extra switches หรือ false trigger ในชุดนี้ และค่าเฉลี่ยการเปลี่ยน command ต่ำกว่า (`0.00120` เทียบกับ `0.00864`). ผลจึงแสดง trade-off ระหว่างความเร็วกับความนิ่ง ไม่ได้แปลว่าตัวใดดีที่สุดทุกเกณฑ์

C0 ทำงานตามเวลา ไม่ได้อ่าน sensor; latency และ false trigger ของ C0 จึงสะท้อนความไม่ตรงกันระหว่าง schedule ที่กำหนดกับ physical crossing ใน scenario ไม่ควรตีความเหมือนการตอบสนองแบบ feedback. C3 มี recovery time เฉลี่ยต่ำสุดในชุดเปรียบเทียบ (`0.109 s`) และ command เปลี่ยนเฉลี่ย `0.00465` ต่อ sample.

## ผลของ noise และ delay ต่อ C2

ตัวเลข latency เป็นค่าเฉลี่ยจาก 5 trials; invalid samples เป็นค่าเฉลี่ยจำนวนตัวอย่างต่อ trial:

| Noise sigma (m) | Delay (ms) | Enter latency (s) | Exit latency (s) | Recovery (s) | False trigger (/min) | Invalid samples |
|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | 0 | 0.423 | 0.417 | 0.423 | 0.00 | 0 |
| 0.00 | 100 | 0.523 | 0.517 | 0.523 | 0.00 | 5 |
| 0.00 | 300 | 0.723 | 0.717 | 0.723 | 0.00 | 15 |
| 0.01 | 0 | 0.431 | 0.417 | 0.434 | 0.00 | 0 |
| 0.01 | 100 | 0.487 | 0.537 | 0.543 | 0.00 | 5 |
| 0.01 | 300 | 0.703 | 0.713 | 0.753 | 0.00 | 15 |
| 0.03 | 0 | 0.407 | 0.353 | 0.410 | 0.00 | 0 |
| 0.03 | 100 | 0.423 | 0.477 | 0.495 | 0.00 | 5 |
| 0.03 | 300 | 0.599 | 0.605 | 0.641 | 0.00 | 15 |

เมื่อ noise คงที่ `sigma = 0.00 m`, การเพิ่ม delay จาก 0 เป็น 300 ms เพิ่ม enter latency จาก `0.423` เป็น `0.723 s` (ประมาณ `0.300 s`) และเพิ่ม invalid samples จาก 0 เป็น 15 ต่อ trial. เมื่อมี noise ค่าเฉลี่ย latency ไม่เพิ่มเป็นเส้นตรงตามระดับ noise ใน 5 trials; ตัวอย่างที่ delay 0 ค่า enter latency เท่ากับ `0.431 s` ที่ sigma 0.01 และ `0.407 s` ที่ sigma 0.03. จึงยังสรุปไม่ได้ว่า noise สูงทำให้ latency เฉลี่ยสูงขึ้นจากชุดนี้เพียงอย่างเดียว. C2 มี false trigger เป็นศูนย์และ extra switches เป็นศูนย์ในทุกชุด robustness ที่รัน.

## กราฟตัวอย่าง

กราฟแต่ละภาพแสดงระยะจริง, raw/filtered sensor, threshold, state, command และตำแหน่ง event ของ trial ตัวอย่างหนึ่ง (ไม่ใช่ค่าเฉลี่ยทุก trial).

### C1: single threshold, sigma 0.01 m, delay 0 ms

![กราฟ trial ตัวอย่าง C1](results/student_comparison/C1_trial1.png)

### C2: filter + hysteresis, sigma 0.01 m, delay 0 ms

![กราฟ trial ตัวอย่าง C2](results/student_comparison/C2_trial1.png)

## อภิปรายและข้อจำกัด

ในชุด C3 ทั้ง 5 trials command อยู่ในช่วง `-0.532` ถึง `0.246`; ไม่มี sample ใดแตะขีดจำกัด `-0.6` หรือ `0.6`. ค่า mean absolute command change บอกความเปลี่ยนแปลงของ command แต่ simulator นี้ไม่มี plant dynamics ที่ใช้คำนวณว่าคำสั่งทำให้ระยะจริงติดตาม target ได้ดีเพียงใด จึงไม่ควรอ้างว่า smoothness สัมพันธ์กับ tracking error จากข้อมูลชุดนี้. ไม่พบ invalid samples ใน controller-comparison ที่ delay 0; ใน robustness ค่าเฉลี่ยจำนวน invalid samples เพิ่มเป็น 5 และ 15 เมื่อ delay เป็น 100 และ 300 ms ตามลำดับ. ใน simulator invalid/stale sample ถูกจัดการด้วย safe command เป็นศูนย์และคง state เดิม.

ข้อจำกัดสำคัญคือใช้เพียง 5 trials ต่อ condition, prediction ก่อนทดลองไม่ได้บันทึกไว้, และ simulator ไม่มี dynamics จาก command กลับไปยังระยะ. ผลนี้เป็น proposed course model ไม่ใช่ค่าความปลอดภัยหรือการรับรองสำหรับหุ่นยนต์จริง.

## สรุป

ภายใต้ค่าทดลองนี้ C1 ให้ latency ต่ำ แต่ไวต่อ noise และเกิดการสลับสถานะมาก; C2 ลด false trigger และการสลับสถานะได้ โดยแลกกับ latency/recovery ที่ยาวขึ้น. การเพิ่ม sensor delay มีผลต่อ latency อย่างชัดเจน และทำให้เกิด invalid/stale samples. ก่อนนำแนวคิดไปใช้กับฮาร์ดแวร์จริง ต้องตรวจ sensor, command unit, mechanical limits และ emergency stop ตามคู่มือแล็บ.

## ไฟล์ผลทดลอง

- [ผลรวม C0–C3](results/student_comparison/summary_aggregate.csv)
- [ผลราย trial C0–C3](results/student_comparison/summary_trials.csv)
- [การตั้งค่าและแผน C0–C3](results/student_comparison/run_config.json)
- [ผลรวม C2 noise/delay](results/student_robustness_full/summary_aggregate.csv)
- [ผลราย trial C2 noise/delay](results/student_robustness_full/summary_trials.csv)
- [การตั้งค่าและแผน C2 noise/delay](results/student_robustness_full/run_config.json)
- [รายงานตรวจ controller](results/student_grade.json)
