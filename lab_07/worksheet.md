# Lab07 student worksheet

ชื่อกลุ่ม: ภาคีนกอีก๋อย สมาชิก: วทัญญู ชำนาญ (6752500096), ณัฐพงศ์ เวชยานนท์ (6752500177), นิธิวัฒน์ สุทธิ (6752500037), ปุญญพัฒน์ ปราณีชาติ (6752500355) วันที่: 11/12/2026 policy version/SHA: DB2AEFEDA2A41DD0E2D7871867037EEBD742DFC1F2C4770FAE0B27D4627A297D

1. วาด source→interaction/FSM→servo/RGB graph; แสดง MCU/Agent extension ที่ต้องทำและเจ็ด topics/types/units/QoS: Graph: synthetic_inputs → interaction (Engine/FSM) → output_collector โดยมี 7 topics ทั้งหมดใช้ QoS RELIABLE, KEEP_LAST 10, VOLATILE: button/touch (Bool), distance (Float32, m), interaction/emotion (String), servo_command (Float32MultiArray, rad [tilt, extend, nod]), rgb_command (ColorRGBA, 0..1, alpha=1) ส่วนที่ต้องสร้างเพิ่มคือ ESP32 + micro-ROS แทน inputs, micro-ROS Agent บน Ubuntu และ servo/RGB driver แทน collector ไม่มี Header ใน 7 topics
2. ตรวจ rad `[tilt,extend,nod]`, normalize RGB/255, alpha1; ยกตัวอย่างคำสั่งและแผน hardware calibration:Servo เป็น rad ลำดับ [tilt, extend, nod] ตัวอย่าง afraid = [-0.22, -0.22, -0.16] RGB = ค่า 0–255 หาร 255, alpha=1 ตัวอย่าง normal (60,90,140) → (0.235, 0.353, 0.549, 1.0) Calibration: วัดมุมจริงเทียบมุมที่สั่งและหา offset, ตั้ง limit ตามกลไก, เพิ่ม watchdog และตัวจำกัดความเร็วด้วยเวลาจริง, เทียบสี RGB จริง, ทดสอบโดยไม่มีคนใกล้ และมีคนคุมปุ่มหยุด
3. ประกาศ question/hypothesis, expected inputIDs, condition/control และ clock/measurement boundary ก่อนรัน: Expected IDs: button_01, touch_01, approach_01, clear_01, near_01, clear_02, button_02
Condition/control: C0 = ส่งแบบอุดมคติ, C1 = delay 0–0.18 s + drop 8% + burst 12.5–12.7 s; ใช้ policy, stimuli, seed 41/42/43 และพารามิเตอร์เดียวกัน
Boundary: เวลาเสมือนใน process เดียว วัดจุดที่คำสั่งถูก apply ครั้งแรก ไม่ใช่ ROS/DDS หรือ hardware
4. รันสามpairedrepeats; บันทึก command/config/trace/manifest path แบบ repository-relative และ metricdenominator: results/completed_run/ (มี input_trace.csv, command_trace.csv, events.csv, metrics.json, config.json ต่อ trial และ summary.json, manifest.json)
Policy SHA256: [วาง hash จาก terminal]
Denominator: primary 7 IDs ต่อ trial; ที่ไม่พบนับเป็น missing ไม่ใช่ 0

| Pair/seed | C0metric1 | C1metric1 | C0metric2 | C1metric2 | Missing/censored | Interpretation |
|---|---|---|---|---|---|---|
| 1/41 | 7/7| 6/7| 0.14| 0.20| C1: missing 1 input; censored 15 msgs| C1 พลาด 1 input|
| 2/42 | 7/7| 6/7| 0.14| 0.22| C1: missing 1 input; censored 9 msgs| C1 พลาด 1 input|
| 3/43 | 7/7| 7/7| 0.14| 0.18| C1: missing 0; censored 12 msgs| ตอบครบ แต่ช้ากว่า C0|

5. แยก invalid/stale baselineprobe จาก communicationstress; อธิบายว่า composite jitter+dropยังตอบเหตุแยกแต่ละส่วนไม่ได้อย่างไร:Invalid/stale probe คือ invalid_01 (ระยะเป็น NaN) กับ stale_01 (ข้อมูล touch เก่า 0.5 s) ซึ่งมีเหมือนกันทั้ง C0 และ C1 จึงเป็นค่าพื้นฐาน (C0 มี fault ticks 20/1101) ส่วนที่เกินใน C1 (54, 81, 56 ticks) มาจาก communication stress

แยกสาเหตุไม่ได้ เพราะ C1 เปลี่ยน delay และ drop พร้อมกัน และทั้งสองอย่างทำให้ข้อมูลเก่าเกิน 0.12 s ได้ จึงบอกไม่ได้ว่า fault ticks ส่วนเกินมาจากตัวไหน ต้องทดลอง delay-only และ drop-only แยกกัน
6. อธิบายสิ่งที่ Bool/Stringไม่มี timestampทำให้สรุปไม่ได้ และเสนอ identity/clocksync/errorbound/physicalmeasurement plan:Bool/String/Float32/ColorRGBA ไม่มี Header (ไม่มี timestamp) ผู้รับรู้แค่เวลาที่รับ ไม่รู้เวลาที่เซนเซอร์อ่านค่า จึงสรุปไม่ได้ว่า (1) ข้อมูลเก่าที่ส่งซ้ำยังดูใหม่, (2) latency จากต้นทางถึง servo/RGB จริง (source_latency_s = N/A), (3) เวลาที่ collector รับ ไม่ใช่เวลาที่ servo ขยับหรือไฟเปลี่ยนสี
แผน: ใส่ input ID + sequence ใน log wrapper (sidecar), sync clock ระหว่าง ESP32 กับ PC แล้วรายงาน error bound, วัดที่ actuator จริง (วิดีโอความเร็วสูง/photodiode), และเพิ่มตัวนับ sequence/timestamp ตอนอ่านเซนเซอร์บน ESP32 เพื่อตรวจข้อมูลเก่า
7. เขียน proposal2–3หน้าและกรอก proposal.json: AHM≥1, SO(2)CPG, integration,≥2conditions,≥2metrics,≥3repeats/condition, simulation AND realrobot, human scenario600s, safety/calibration/controls/timeline: __________

Checklist: [ ] graph7topics [ ] units/QoS [ ] completed policy checker [ ] rawdata/config/SHA [ ] pairedprotocol [ ] misses [ ] measurementlimitations [ ] completeproposal
