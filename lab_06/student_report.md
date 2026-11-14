# Lab 06 — Lamp Emotion and Interaction

## ข้อมูลผู้จัดทำและขอบเขต

- ชื่อ: ภาณุพร มาศรี
- รหัสนักศึกษา: 6752500118
- กลุ่ม: —
- Python: 3.12.10
- วันที่บันทึกคำทำนาย: 2026-11-14
- สถานะตอนบันทึกส่วนนี้: ยังไม่ได้รัน paired trials หรือเปิด metrics

งานนี้ใช้ finite-state machine ใน proposed course model ไม่มี persistent learning และ joint เป็นแกนเชิงความหมาย ไม่ใช่ linkage/torque ของหุ่นจริง

## Transition table ที่ประกาศก่อนรัน

`hold` หมายถึง `transition()` คืน `None`; engine จึงคง state เดิม ลำดับ safety guard คือ fault → near → clear แล้วจึงใช้ mapping อื่น

| current state | fault | near | clear | touch | button | approach | timeout | idle |
|---|---|---|---|---|---|---|---|---|
| normal | normal | afraid | normal | happy | interested | interested | hold | sleepy |
| interested | normal | afraid | normal | happy | interested | interested | normal | hold |
| happy | normal | afraid | normal | happy | interested | interested | normal | hold |
| afraid | normal | afraid | normal | hold | hold | hold | hold | hold |
| sleepy | normal | afraid | normal | happy | interested | interested | hold | hold |

ชุด primary expected IDs ตรึงไว้ 7 รายการก่อนรัน ได้แก่ `button_01`, `touch_01`, `approach_01`, `clear_01`, `near_01`, `clear_02`, `button_02` และใช้ชุดเดียวกันกับ C0/C1 ทั้งสาม repeat

## คำทำนายก่อนทดลอง

1. C1 ที่มี debounce/hysteresis น่าจะลด transition จาก button bounce และ distance noise แต่แลกกับ recognition latency และอาจพลาด input ที่สั้นกว่า debounce window
2. near และ touch ที่เกิดใกล้กันต้องจบเป็น `afraid` เพราะ near มี priority สูงกว่า และ touch ระหว่าง afraid ต้อง hold
3. distance invalid หรือ timestamp stale ต้องเรียก neutral fallback เป็น `normal`
4. ช่วงเงียบปลาย trial ควรทำให้ normal เข้า `sleepy` ก่อน `button_02` ปลุกกลับเป็น `interested`
5. Latency ที่รายงานต้องนับจาก source time ถึง output onset จริงใน model; input ที่ไม่มี state/output ใหม่ต้องเป็น N/A พร้อมเหตุผล ไม่แทนด้วย 0

## วิธีทดลองและผล

ก่อนทดลองรัน checker ทั้ง baseline และ group contract; ทั้งสองแบบตรวจ 40 คู่และได้ 0 failures จากนั้นใช้คำสั่ง

```powershell
py -3 lab06.py --policy student --condition all --repeats 3 --output-dir results\double_completed
py -3 lab06.py --policy student --condition C1 --repeats 1 --replay results\double_completed\inputs_r01.csv --output-dir results\double_replay
```

ผลทั้ง 10 source inputs และ primary denominator 7 รายการเป็นดังนี้ `all both` และ `primary pass` คือจำนวนที่มีทั้ง motion/RGB onset และผ่านเกณฑ์จำลองไม่เกิน 1 s

| condition / seed | all sources | all both | all missing | primary pass/7 | primary missing | max observed latency (s) | state transitions |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 / 41 | 10 | 7 | 3 | 7/7 | 0 | 0.24 | 67 |
| C1 / 41 | 10 | 7 | 3 | 7/7 | 0 | 0.14 | 9 |
| C0 / 42 | 10 | 6 | 4 | 6/7 | 1 | 0.18 | 72 |
| C1 / 42 | 10 | 7 | 3 | 7/7 | 0 | 0.14 | 10 |
| C0 / 43 | 10 | 6 | 4 | 6/7 | 1 | 0.04 | 63 |
| C1 / 43 | 10 | 7 | 3 | 7/7 | 0 | 0.14 | 9 |

ทุก run เข้าถึงทั้งห้า state. Primary ที่ C0 พลาดคือ `clear_01` ของ seed 42 (`filtered_not_recognized`) และ `clear_02` ของ seed 43 (`no_state_change`) ส่วน C1 ได้ 7/7 ทุก seed

ตารางต่อไปแสดง all-source outcomes ของ C1/seed 41 โดย N/A หมายถึงไม่มี output onset ใหม่ตามเหตุผล ไม่ใช่ latency ศูนย์

| input ID | kind | source (s) | primary | both onset (s) | both latency (s) | status |
|---|---|---:|:---:|---:|---:|---|
| button_01 | button | 1.00 | yes | 1.14 | 0.14 | responded |
| touch_01 | touch | 3.00 | yes | 3.10 | 0.10 | responded |
| approach_01 | approach | 5.00 | yes | 5.04 | 0.04 | responded |
| clear_01 | clear | 6.40 | yes | 6.44 | 0.04 | responded |
| touch_conflict | touch | 7.00 | no | N/A | N/A | policy_held |
| near_01 | near | 7.00 | yes | 7.04 | 0.04 | responded |
| clear_02 | clear | 9.00 | yes | 9.04 | 0.04 | responded |
| invalid_01 | fault | 11.00 | no | N/A | N/A | no_state_change |
| stale_01 | fault | 12.00 | no | N/A | N/A | no_state_change |
| button_02 | button | 18.00 | yes | 18.10 | 0.10 | responded |

ตัวอย่าง trace ของ `button_01`: source=1.00 s, recognized/decision/queued=1.10 s, actual apply=motion onset=RGB onset=1.14 s จึงได้ both latency=0.14 s. Near กับ touch เวลา 7.00 s จบที่ afraid; near responded ส่วน touch เป็น `policy_held`. Invalid และ stale ถูกตีความเป็น fault แต่ขณะนั้น output เป็น neutral อยู่แล้วจึง `no_state_change`. หลังไม่มี interaction normal เข้าสู่ sleepy ที่ 15.04 s และ `button_02` เปลี่ยน sleepy → interested ที่ 18.10 s ตามคำทำนาย

Replay สร้างไฟล์เหมือนต้นฉบับแบบ byte-for-byte:

- `raw_C1_r01.csv`: SHA-256 `3cbe847c7a4826b94263c88caeb6a7751b306f56f9eb8caae0d6dcdbeab41ff4` ทั้งคู่
- `events_C1_r01.csv`: SHA-256 `1942cd3bc6addcf205261671f6fc5d21955f0260503b56893135f301fef53994` ทั้งคู่

## อภิปรายผลและข้อจำกัด

C1 ลด state transitions จาก 63–72 ครั้งใน C0 เหลือ 9–10 ครั้ง แสดงว่า debounce/hysteresis ลดการตอบสนองซ้ำจาก bounce/noise ใน synthetic input ชุดนี้ ขณะเดียวกัน `button_01` ของ C1 ต้องรอ debounce จึงมี latency 0.14 s; C0 บาง seed ตอบได้เร็วกว่า ดังนั้น filter มีต้นทุนด้านเวลา ผล primary 7/7 ของ C1 สนับสนุนประโยชน์ใน protocol นี้ แต่ไม่ได้แปลว่าจะไม่พลาด pulse ที่สั้นกว่า 0.06 s

ผลที่ไม่ต่างคือ seed 41 ให้ all-source both onset 7/10 เท่ากันทั้ง C0 และ C1 และทุก run ยังมีสาม source ที่ตั้งใจไม่มี onset ได้แก่ conflicting touch กับ fault สองรายการที่ neutral อยู่แล้ว การนับเฉพาะ event ที่ตอบสนองจะทำให้ดูสำเร็จเกินจริง จึงคง denominator 10 และเหตุผล missing ไว้

ข้อมูลทั้งหมดเป็น synthetic replications จาก seeds 41–43 ไม่ใช่ physical trials. simulated latency วัด scheduler และ bounded output ใน software เท่านั้น; ยังไม่มี USB/network jitter, motor dynamics, camera/photodiode timing หรือ clock synchronization ระหว่าง sensor และ actuator ก่อนอ้าง response time ของหุ่นจริงต้องวัด motion กับ RGB แยกกันด้วย clock ที่สอบเทียบ พร้อม resolution และ uncertainty
