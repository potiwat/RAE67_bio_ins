# Lab07 student worksheet

ชื่อกลุ่ม: 7 | วันที่: 5 พฤศจิกายน 2569  
Policy: FSM 6 อารมณ์ + scripted input v2; `lab_fsm.py` SHA256 `f55affe1a8e51ecfdd4bd827678270d8435df60311ca0537cabe67c40513d9cf`

## 1 วาด source→interaction/FSM→servo/RGB graph และระบุ MCU Agent topics units QoS

![LeLamp architecture](../04_Design/LeLamp_Architecture.png)

[ไฟล์ Draw.io แก้ไขได้](../04_Design/LeLamp_Architecture.drawio)

![ROS course three roles จาก endpoint discovery](../04_Design/COURSE_THREE_ROLES_OBSERVED.png)

กราฟนี้มาจาก course ROS seed41 แบบ synthetic inputs; เป็นอีกหลักฐานหนึ่ง แยกจาก live native Pi telemetry และจากภาพ rosbag replay

![รูปที่ 1 ROS replay graph จากภาพผู้ใช้](../04_Design/ROS_Replay_rqt_graph_USER_20261106.png)

รูปที่ 1: `rosbag2_player → 13 topics` ใต้ `/lamp` เป็น replay จากข้อมูลโคมจริง ไม่มี subscriber ในภาพนี้; `/events/read_split` เป็น topic ของ rosbag ไม่นับใน 13 รายการ


ไม่ใช้ MCU หรือ micro-ROS Agent; Pi ควบคุมมอเตอร์ผ่าน UART owner เดียว ส่วน ROS ใช้ SSH live/recorded telemetry บน WSL; ทดสอบ live934แถว/60.029sครบ13topicsแล้ว.

| Topic | Type | หน่วยหรือความหมาย |
|---|---|---|
| `/lamp/input/button` | `std_msgs/msg/Bool` | pressed true/false |
| `/lamp/input/touch` | `std_msgs/msg/Bool` | pressed true/false |
| `/lamp/input/distance` | `std_msgs/msg/Float32` | m valid only |
| `/lamp/interaction` | `std_msgs/msg/String` | event name |
| `/lamp/emotion` | `std_msgs/msg/String` | 6 state names |
| `/lamp/servo_command` | `std_msgs/msg/Float32MultiArray` | rad [ID4,ID2,ID5] |
| `/lamp/rgb_command` | `std_msgs/msg/ColorRGBA` | RGBA 0–1 |
| `/lamp/input/status` | `std_msgs/msg/String` | JSON input quality / edges |
| `/lamp/ahm_cpg/diagnostic` | `std_msgs/msg/String` | JSON S H R phi o1 o2 mask |
| `/lamp/joint_states` | `sensor_msgs/msg/JointState` | rad 5 joints relative Normal |
| `/lamp/perception/face` | `std_msgs/msg/String` | JSON selected face / time |
| `/lamp/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | status / V / °C / ages |
| `/lamp/trace` | `std_msgs/msg/String` | JSON source / state / goals |

ครบ 13 topics ตาม `04_Design/TOPIC_CONTRACT_13.json`.

ทุก topic ใน live/replay: `lelamp_session_observer → rosbag2_recorder`; ตั้ง RELIABLE / KEEP_LAST depth 10 / VOLATILE ตาม `qos.yaml`. Graph introspection รายงาน history/depth เป็น UNKNOWN/0 จึงไม่ใช้ค่านั้นรับรองค่า QoS.

### Node ที่เก็บ internal state และผู้รับผิดชอบ

Pi ใช้ฟังก์ชันภายใน runtime เดียว: input เก็บตัวกรอง, FSM เก็บสถานะ/เวลา, AHM เก็บ H, CPG เก็บ o1/o2 และ motion owner เก็บท่า ผู้รับผิดชอบร่วมคือกลุ่ม 7; WSL observer ส่ง telemetry ให้ recorder

### เหตุใดใช้ทั้ง AHM และ SO(2) CPG

AHM เก็บความจำของสิ่งเร้า ส่วน CPG สร้างจังหวะ เราใช้ H ปรับ phi จึงใช้ทั้งสองส่วน

## 2 ตรวจ rad normalize RGB alpha และ hardware calibration

`servo_command=[ID4,ID2,ID5]` เป็น rad เทียบ Normal; extend เป็นมุมข้อ ไม่ใช่ cm. ตัวอย่าง `[0.10,0.05,-0.10]` และไฟแดง RGBA `[1,0,0,1]` จาก RGB/255 เป็นตัวอย่าง contract ไม่ใช่คำสั่งให้หุ่นขยับ.

สอบเทียบ Normal ทิศทาง หน่วย และขอบมุมทีละข้อ ตรวจสาย/โครงและ STOP ก่อนขยับร่วมกัน; ไม่ใช้ raw ticks แทน rad.

## 3 Question hypothesis input IDs conditions controls และ clock boundary

**คำถาม:** การปรับ φ ผ่าน H เปลี่ยนความถี่และ ΔT ของ CPG อย่างไรเมื่อเทียบกับการปรับจาก S โดยตรง?  
**สมมติฐาน:** C1 ทำให้จังหวะเปลี่ยนค่อยเป็นค่อยไปกว่า C0.

C0: R=S; C1: R=H; φ=clip(0.10+0.03R,0.10,0.13). คง input grid, H/CPG เริ่มต้น, α=1.10, dt=0.05 s, ท่า/PID/Speed/ACC และ decoder เหมือนกัน.

ต่อ trial มี Button 5 press, Touch 20 press, Near/Clear 5 คู่ และ touch_burst ที่อนุมานอีก 5 events. บันทึก `script_button_*`, `script_touch_*` และ event/source IDs จริง แยกจาก GPIO จริง; ไม่ใช้ชื่ออารมณ์แทน S.

Owner/input ใช้ Pi CLOCK_BOOTTIME; feedback ใช้ CLOCK_MONOTONIC; ROSbag ใช้เวลารับบน WSL. M1/M2 วัดจาก o₁ ไม่ใช่ physical latency.

## 4 สาม paired repeats paths และ metric denominator

Simulation 3 คู่และ real robot 3 คู่ รอบละ 600 s เก็บครบแล้ว. Real ใช้ลำดับ C0→C1 ทุกคู่ จึงยังมี order effect; simulation เป็น deterministic replay ไม่ใช่สามคนทดลองอิสระ.

M1 = 1/mean(T) หน่วย Hz; M2 = mean(|Tₙ−Tₙ₋₁|) หน่วย s ภายใน episode ต่อเนื่อง. ตารางย่อแสดง **Happy ของ real robot**; รายงานครบ 6 อารมณ์ใน CSV 36 แถว ไม่ต่อคาบข้าม state หรือ gap.

| Pair/seed | C0 metric1 Hz | C1 metric1 Hz | C0 metric2 s | C1 metric2 s | Missing/censored และ denominator | Interpretation |
|---|---:|---:|---:|---:|---|---|
| P1 / ไม่ใช้ seed | 0.3164 | 0.3258 | 0.3139 | 0.2589 | T=21/21; คู่ T=16/16; C0 มี ToF hold 1 ครั้ง | Happy ΔT ลดใน C1 |
| P2 / ไม่ใช้ seed | 0.3179 | 0.3224 | 0.3224 | 0.2802 | T=21/22; คู่ T=16/17; C1 มี ToF hold 3 ครั้ง | Happy ΔT ลดใน C1 |
| P3 / ไม่ใช้ seed | 0.3178 | 0.3224 | 0.3275 | 0.2702 | T=20/22; คู่ T=15/17; C1 มี ToF hold 1 ครั้ง | Happy ΔT ลดใน C1 |

T/คู่ T แสดง C0/C1 ตามลำดับ. Interested/Angry มีคาบไม่พอจึงเป็น N/A; Sleepy ให้ผลไม่สม่ำเสมอทุกคู่. ผลนี้ยังไม่ยืนยันความสมูทเชิงกลหรือความแตกต่างทางสถิติ.

Repository-relative paths ในชุดส่ง:

- คำสั่งทดลอง: `02_Source/bio_inspire/deploy/open_lab07_auto.py` (`--condition C0/C1 --pair P1/P2/P3`)
- Config: `02_Source/bio_inspire/hardware/lab07_automatic_P*_C*.json`
- Raw/config/trace/manifest/ROSbag: `03_Results/real_robot_final/P*_C*_data.zip` แต่ละ ZIP มี metadata, trace, CSV และ ROSbag readback audit
- ผลรวม: `03_Results/real_robot_final/SIX_TRIAL_SUMMARY.csv` และ `OBSERVED_O1_METRICS_36_ROWS.csv`
- Simulation: `03_Results/simulation_final/` มี P1–P3 C0/C1 CSV และ source hashes ใน `summary.json`

## 5 แยก invalid stale baseline probe จาก communication stress

Invalid/stale เป็นการตรวจคุณภาพ input; communication stress คือการฉีด delay/jitter/drop. ชุด AHM ล่าสุดไม่ได้ใช้ communication stress เป็นตัวแปรทดลอง. การรวม jitter+drop แยกผลของแต่ละปัจจัยไม่ได้ ต้องทดสอบแต่ละปัจจัยและกรณีร่วมแยกกัน.

## 6 Bool String ไม่มี timestamp ทำให้สรุปอะไรไม่ได้

Bool/String ไม่มี source timestamp จึงวัด source-to-physical latency จากเวลารับอย่างเดียวไม่ได้. เก็บ run/source/event ID และเวลาแต่ละจุด; หากข้ามเครื่องต้อง sync clock วัด error bound และตรวจ physical onset จาก encoder/วิดีโอ. การสอบเทียบ onset ยังเป็น N/A.

## 7 Proposal และสถานะส่ง

มี proposal 3 หน้า ใบงาน Word สรุปผล และหลักฐาน AHM–SO(2), C0/C1, M1/M2, simulation/real อย่างละ 3 คู่แล้ว. `proposal.json` และ completed policy ผ่าน checkerแล้ว; ผู้รับผิดชอบร่วมตามแผนคือกลุ่ม7ตามรายชื่อ วันส่งอ้างใบงาน6/11/2569. คลิปทดลองเล่นยาว 167.05 s เป็นหลักฐานประกอบ; real robot ทดลองรอบละ 600 s ด้วย scripted input และคนอยู่หน้ากล้อง ไม่พบข้อกำหนดว่าต้องถ่ายคลิปยาว 10 นาที.

Checklist: [x] graph7topics [x] units/QoS [x] completed policy checker [x] rawdata/config/SHA [x] pairedprotocol [x] misses [x] measurementlimitations [x] completeproposal

Teacher bridge: completed policy40/40; expected C0ผ่าน21/21,C1ผ่าน19/21 เก็บmisses2ตามจริงใน course_bridge_verified_20261026_27 เป็นผลtransport แยกจากAHMที่ใช้จำนวนคาบ/คู่คาบเป็นdenominator. ระบบกลุ่มใช้ Pi 5 ควบคุมโคม และ ROS บน WSL รับข้อมูลผ่าน SSH ไม่มี MCU แยกหรือ micro-ROS Agent ในขอบเขตงานนี้.

### ความเสี่ยงสำคัญและสิ่งที่ต้องตรวจถัดไป

เสี่ยงสายตึง/ชนและ ToF ไม่สด; ตรวจขอบมุมกับ STOP ก่อนใช้ และวัดการตอบสนองมอเตอร์จริงในงานต่อไป
