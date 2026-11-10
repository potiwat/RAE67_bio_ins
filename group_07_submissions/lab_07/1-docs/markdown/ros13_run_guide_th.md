# ROS13 การบันทึกข้อมูล Lab07

## ขอบเขต

Pi มี Python/UART owner เดิมและ logger; WSL Ubuntu24.04/ROS2 Jazzy เป็น observation publisher และ rosbag2 recorder ไม่ได้เพิ่ม actuator subscriber และไม่เปลี่ยนท่า/PID/ความเร็ว/ความเร่งของโคม การทดสอบ virtual ROS ผ่านไม่เท่ากับผล physical latency หรือผลทดลองวิจัยบนโคมจริง

ผู้ใช้อนุมัติ semantic สำหรับบันทึก 5พ.ย.2026: [tilt,extend,nod]=command offset ของ [ID4,ID2,ID5] หน่วยrad อ้าง Normal; extend เป็นมุม ID2 ไม่ใช่ระยะcm ไม่ใช่ FK/IK หรือ inverse driver สำหรับมอเตอร์ทั้ง5ตัว เก็บ measured ทั้ง5แยกใน joint_states และ cached goals ทั้ง5ใน trace

## ครบ13 topics

| Topic | Type | ข้อมูล |
|---|---|---|
| /lamp/input/button | std_msgs/msg/Bool | stable level; source edges ใน input/status |
| /lamp/input/touch | std_msgs/msg/Bool | stable level; source edges ใน input/status |
| /lamp/input/distance | std_msgs/msg/Float32 | m; ส่งเฉพาะrange valid; ไม่มีวัตถุไม่ส่ง0 |
| /lamp/interaction | std_msgs/msg/String | event name ตาม FSM; IDs/status ของ candidate ทุกอันในtrace |
| /lamp/emotion | std_msgs/msg/String | actual FSM state ทั้ง6 |
| /lamp/servo_command | std_msgs/msg/Float32MultiArray | semantic rad [ID4,ID2,ID5] relative Normal |
| /lamp/rgb_command | std_msgs/msg/ColorRGBA | commanded RGB/255,alpha1; brightness.03แยกdiagnostics ไม่ใช่การวัดแสงจริง |
| /lamp/input/status | std_msgs/msg/String | JSON atomic source/index/raw/stable edges/ToF quality/time |
| /lamp/ahm_cpg/diagnostic | std_msgs/msg/String | JSON active oscillator/S/H/R/phi/owner/envelope/mask |
| /lamp/joint_states | sensor_msgs/msg/JointState | positionrad5ข้ออ้างNormal; velocity/effortว่างเมื่อไม่คาลิเบรต |
| /lamp/perception/face | std_msgs/msg/String | JSON selected face/error/normalized box/capture time/scan-handoff |
| /lamp/diagnostics | diagnostic_msgs/msg/DiagnosticArray | owner/motorstatus/voltageV/tempC/current_raw/load_raw/ages/stopreason |
| /lamp/trace | std_msgs/msg/String | JSON source/event/run/pair/condition/stage/5rawgoals/FSM |

ทุกtopicใช้ Reliable/KeepLast10/Volatile; บันทึก actual discovery/QoS ใน ros_graph_qos.json ไม่ใช้ /rosout หรือ /parameter_events เพิ่มจำนวน13

## วิธีใช้

1. รันหน้าต่างเดิมบน Pi ด้วย lab07_r37_C0_30s.json หรือ C1_30s.json แทน profileเล่นปกติ ยังรอ Start/M ไม่สั่งขยับตอนเปิด
2. Start แล้ว READY/Normal คือ t0 ของ logger; pilot30s: t5ปุ่มฐาน.2–.4s, t15Touch.5s, t22–24Nearแล้วเอาออกให้Clear หลังครบ30sรองรับแล้ว Q
3. ส่ง directoryของsessionจาก Pi มาใน bio_inspire/results โดยเก็บ metadata.json,summary.json,trace.jsonl แบบไม่แก้raw ไม่ใช้ last_status snapshot แทนstreamเต็ม
4. บน WSL ที่ source ROS Jazzyแล้ว:

```bash
cd /mnt/c/Users/USER/Desktop/Project/Lamp
source /opt/ros/jazzy/setup.bash
python3 -B -m bio_inspire.experiments.ros13_record --session bio_inspire/results/<session> --out bio_inspire/results/<new_ros_out> --pair-id pilot_P1
```

เปลี่ยนsession/outให้เป็นชื่อจริง outต้องยังไม่มี รหัส pairของการทดลองจริงต้องกำหนดก่อนเก็บ ใช้ --live ได้เมื่ออ่าน growing file ที่ mirrorครบ/ต่อเนื่องในเครื่องWSL แต่โหมดที่ทดสอบตอนนี้เป็น finalized session replay อย่าอ้างว่าROSสั่งมอเตอร์หรือเป็น live network latency

## หลักฐานที่ได้และเกณฑ์ผ่าน

- bag/metadata.yaml และ sqlite3 db3 เปิดอ่านด้วย rosbag2ได้
- source_metadata.json, ros_graph_qos.json, qos.yaml, publisher_ledger.jsonl
- published_counts.json และ verification.json ตรวจครบ13types/count/decoded-fields SHA256 หลัง Float32 quantization หลีกเลี่ยงเทียบ CDR padding ที่ไม่ใช่ข้อมูล
- manifest.json เก็บSHA256ไฟล์ผล; verificationเก็บhashrawและbridge source
- PASS ต้องทุกtopicมีข้อความและcount/hashตรงกับpublished ledger, source complete ไม่มีdrop/error, sourcehashตรงและpairassigned
- ถ้าไม่มีrangevalidหรือinteractionจริง topicนั้นอาจไม่มีข้อความ ต้องรายงานINCOMPLETEสำหรับcoverageของpilot ไม่แต่งeventหรือส่ง0เพื่อให้จำนวนครบ
- STOP/FAULT/ปิดก่อนเวลา/คิวตกทำให้source incomplete ข้อมูลเก็บไว้ตรวจ ไม่ลบทิ้ง

Header joint_states ใช้เวลา snapshot ของownerใน source clock ส่วน sampled_monotonic_s รายข้อในdiagnostics เป็นPi CLOCK_MONOTONIC ต้องไม่ถือว่าเท่ากับCLOCK_BOOTTIMEโดยไม่วัด ROS bag timestamps เป็นเวลารับบนWSLต่างclock ไม่ใช่physical onset

## ขนาดและงานที่ยังต้องยืนยัน

writerคิว256 ไม่เกิน20,000แถว/64KiBต่อแถว/128MiBต่อtrace ปรับจาก64MiBหลังพบข้อมูล13topicsมีแนวโน้มใช้ราว93MBต่อ600s ทดสอบcapacity12,001แถวบนคอมผ่านโดยไม่มีdrop เป็นsoftware stress ไม่ใช่ผลC0/C1

ก่อนfinal3คู่: pilotโคมจริง/ROS13ต้องผ่าน, matched H/phase ณlogger t0ยังต้องตรวจ, วิดีโอและphysical timing uncertaintyยังต้องวัด การบันทึกครบไม่ใช่การยืนยันว่าผลวิจัยC1ดีกว่าC0


อัปเดตหลักฐานล่าสุด: hardware C1 pilot30s เก็บ361แถวแล้ว replay→WSL rosbagครบ13topic count/hashตรง ไม่มีdrop; ดู bio_inspire/results/ros13_20261105/REPORT_TH.md ไม่ใช่final3คู่ และยังต้องตรวจC0ตามprotocolเดียวกัน ผู้เล่นยืนยันInterested/Happyหลังแก้แล้ว; WAIT_TOFสดคลุมเครือ.5sคืนNormalและresettimerเมื่อerrorทั้งก่อน/หลังfeedback เทสPi66ผ่าน
