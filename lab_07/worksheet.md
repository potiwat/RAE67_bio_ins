# Lab07 student worksheet

ชื่อ นายจิรายุส พลอยพริ้ง   รหัสนักศึกษา 6752500401   วันที่: __________   policy version/SHA: lamp_week07/student_policy.py SHA256 21e94b3678b15981…

1. วาด source→interaction/FSM→servo/RGB graph; แสดง MCU/Agent extension ที่ต้องทำและเจ็ด topics/types/units/QoS: `figures/ros2_graph.png` 3 roles + ESP32/micro-ROS Agent (ส่วนขยาย) 7 topics: button/touch Bool, distance Float32 m, interaction/emotion String, servo_command Float32MultiArray [tilt, extend, nod] rad, rgb_command ColorRGBA 0–1; QoS RELIABLE, KEEP_LAST 10, VOLATILE
2. ตรวจ rad `[tilt,extend,nod]`, normalize RGB/255, alpha1; ยกตัวอย่างคำสั่งและแผน hardware calibration: เช่น interested = [0.22, 0.18, 0.06] rad และ RGB (255, 180, 0)/255 = (1.000, 0.706, 0.000, a = 1); สอบเทียบ neutral, ทิศทาง, bounds และ rad → PWM ทีละแกนก่อนขับ servo จริง
3. ประกาศ question/hypothesis, expected inputIDs, condition/control และ clock/measurement boundary ก่อนรัน: question/hypothesis อยู่ใน proposal.json; expected IDs = baseline 7 (button_01, touch_01, approach_01, clear_01, near_01, clear_02, button_02); C0 ideal vs C1 delay+drop ใช้ policy เดียวกัน; offline วัด applied command ใน virtual clock เท่านั้น ไม่ใช่ physical onset
4. รันสามpairedrepeats; บันทึก command/config/trace/manifest path แบบ repository-relative และ metricdenominator: `python offline_lab.py --condition all --repeats 3 --output-dir results/completed_starter` (results/completed_starter/<C>_r0N/{input_trace,command_trace,events}.csv, config.json, manifest.json); metric1 = primary pass ≤ 1 s จาก 7 IDs, metric2 = state transitions ต่อ trial (22 s)

| Pair/seed | C0metric1 | C1metric1 | C0metric2 | C1metric2 | Missing/censored | Interpretation |
|---|---|---|---|---|---|---|
| 1/41 | 7/7 | 6/7 | 9 | 17 | C1 miss clear_02; C1 dropped 257, censored 15 | C1 ทำให้พลาด 1 input และ state สลับมากขึ้น |
| 2/42 | 7/7 | 6/7 | 10 | 36 | C1 miss button_02; dropped 287, censored 9 | ผลแย่ที่สุดใน 3 คู่ |
| 3/43 | 7/7 | 7/7 | 9 | 17 | ไม่มี miss; dropped 300, censored 12 | ผ่านครบแต่ state สลับมากขึ้น |

5. แยก invalid/stale baselineprobe จาก communicationstress; อธิบายว่า composite jitter+dropยังตอบเหตุแยกแต่ละส่วนไม่ได้อย่างไร: invalid/stale probes มีเท่ากันทั้ง C0/C1 (C0 fault ticks = 20 ทุก seed) ส่วนที่เกินใน C1 (54, 81, 56) มาจาก communication stress แต่ C1 เปลี่ยน delay และ drop พร้อมกัน จึงบอกไม่ได้ว่าผลมาจากส่วนไหน ต้องรัน delay-only และ drop-only แยก
6. อธิบายสิ่งที่ Bool/Stringไม่มี timestampทำให้สรุปไม่ได้ และเสนอ identity/clocksync/errorbound/physicalmeasurement plan: Bool/String ไม่มี Header จึงไม่รู้ source time และ local_sequence ของ publish/receive ไม่ใช่ ID เดียวกัน (ROS run: inputs publish 1,101 แต่ interaction รับ 1,097–1,098 บอกไม่ได้ว่าข้อความไหนหาย) source_latency_s จึงเป็น N/A; แผน: log wrapper ใส่ input_id, sync clock ด้วย ping-pong + error bound, วัด onset ด้วย IMU/photodiode/กล้อง
7. เขียน proposal2–3หน้าและกรอก proposal.json: AHM≥1, SO(2)CPG, integration,≥2conditions,≥2metrics,≥3repeats/condition, simulation AND realrobot, human scenario600s, safety/calibration/controls/timeline: อยู่ใน `proposal.json` (check_proposal PASS) และ `Week07_Proposal_TH.docx` (3 หน้า)

Checklist: [x] graph7topics [x] units/QoS [x] completed policy checker [x] rawdata/config/SHA [x] pairedprotocol [x] misses [x] measurementlimitations [x] completeproposal

## ROS 2 run

เครื่องนี้เป็น Windows จึงรันส่วน ROS 2 บนเครื่องที่ยืมเพื่อนตามที่อาจารย์อนุญาต (ROS 2 Jazzy ใน Docker container Ubuntu 24.04) ใช้ policy ที่ตาราง 5×8 ตรงกับของผมทั้ง 40 ช่อง รัน seed 41, 42, 43 (`figures/ros_machine_run01_topics.png`, `figures/ros_machine_runs_bag.png`) และวิเคราะห์ log บนเครื่องนี้ (`figures/ros_logs_analysis.png`): inputs publish 1,101 ข้อความต่อ topic, interaction รับ 1,097–1,098, collector รับ 1,354/1,356/1,335 จาก 1,354/1,359/1,359, bag run01 มี 8,694 ข้อความใน 27.02 s, ลำดับ emotion ตรงกับ protocol แต่ run02 ช้ากว่า run01 ราว 0.6 s เพราะเริ่มรับข้อความช้า 0.39 s
