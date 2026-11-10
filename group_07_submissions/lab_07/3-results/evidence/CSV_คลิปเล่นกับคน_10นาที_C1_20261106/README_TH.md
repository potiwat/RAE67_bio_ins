# CSV ของคลิปเล่นกับคน 10 นาที — C1

รอบจริงบนโคม: `20261106T044600Z_6ba96b37` / pair `human_play_C1_20261106_r01`

ผู้ใช้กด M ตั้ง Normal แล้วกด–ปล่อยปุ่มฐาน 5 ครั้งเพื่อเริ่ม ไฟเปิดเป็น marker ผู้ใช้เล่นกับโคมตามปกติ ไม่มี scripted experimental inputs และกด Q หลังครบ10นาที คงท่า/PID/Speed/Acceleration เดิม

## เปิดไฟล์ไหน

- `CSV_คลิปเล่นกับคน_10นาที.csv`: ภาพรวม7,098แถว เวลา/state/behavior/Button/Touch/ToF/face/S/H/phi/o1/o2/error จาก runtime
- `ROS13_MESSAGES.csv`: ข้อมูล telemetry ครบ13topic รวม85,032message rows พร้อมชื่อtopic/type/data_json
- `TOPIC_COUNTS.csv`: จำนวนmessageแยก13topics
- `JOINT_FEEDBACK.csv`: คำสั่งและencoderครบID1–5 หน่วยraw ticks พร้อมแรงดัน/อุณหภูมิ/statusและเวลาfeedbackแต่ละข้อ
- `trace.jsonl`, `metadata.json`, `summary.json`: ข้อมูลดิบต้นฉบับไม่แก้ไข พร้อมsource/profile hashes
- `SESSION_VERIFICATION.json`, `CSV_EXPORT_AUDIT.json`, `DOWNLOAD_VERIFICATION.json`: ผลตรวจอ่านกลับและhashเทียบPi
- `human_play_C1_600s.json`: โปรไฟล์ที่ใช้จริง

## ผลตรวจ

เก็บได้600.019884547s,7,098snapshots; written=accepted, dropped=0, writer errorและinput health errorไม่มี ตรวจrawSHAตรงPiและตรวจCSVทุกpacketเทียบEncoderเดิมแล้ว พบFSMครบNormal/Interested/Happy/Angry/Afraid/Sleepy

capture_complete=true แต่ clean_complete=false: มีWAIT_TOF4snapshots รวม3ช่วง ที่elapsed152.260–152.916s,183.956–184.464sและ184.680–185.133s รวมช่วงที่สังเกตจากsnapshotประมาณ1.618s ไม่ใช่การวัดphysical stop durationแบบละเอียด โปรแกรมกลับREADYและบันทึกต่อจนครบ ไม่ลบแถวเหล่านี้

จำนวนdistance message6,861น้อยกว่าsnapshot7,098เพราะส่งเฉพาะระยะที่valid ไม่เติมระยะสมมติ; interaction93messageเป็นeventจึงไม่จำเป็นต้องเท่าจำนวนsnapshot

## เวลา หน่วย และข้อจำกัด

elapsed_s ของCSVอ้างsnapshotแรก เวลาmarkerกดปล่อยครั้งที่5และgateเริ่มอยู่ในmeasurement_startของraw/SESSION_VERIFICATION ห้ามถือว่าเวลา0ตรงframeแรกของวิดีโอโดยอัตโนมัติ

owner_time_s ใช้Pi CLOCK_BOOTTIME; feedback_monotonic_sใช้Pi CLOCK_MONOTONIC ไม่ลบข้ามclockเป็นphysical latency feedbackแต่ละข้ออาจมีเวลาต่างกันและอาจถูกอ่านซ้ำในsnapshotถัดไป ให้ใช้timestampประกอบ

servo_command เป็นradเทียบNormal [ID4,ID2,ID5] ส่วนJOINT_FEEDBACKใช้rawencoder ticksตามที่อ่านจริง extendเป็นมุมข้อไม่ใช่cm S/H/phi/o1/o2เป็นสถานะคำนวณของruntime อาจคงค่าระหว่างการพัก; ช่องไม่มีข้อมูลเว้นว่าง ไม่เติม0

CSV13topicsนี้แปลงจากsessionที่บันทึกจริง ไม่ใช่หลักฐานว่ารันROSbagliveระหว่างคลิป และไม่ใช่ROSสั่งมอเตอร์ เป็นรอบC1คนเล่นเพิ่มเติม แยกจากcontrolled C0/C1หกรอบเดิม ไม่ใช้แทนหรือรวมเพิ่มเป็นpaired trial

แนบวิดีโอ `คลิปเล่นกับคน_10นาที_C1.MOV` แล้ว ความยาวตามMOV metadata 610.947s (10นาที10.95วินาที) ตรวจSHA256ตรงต้นฉบับ IMG_5749.MOV ทุกbyte วิดีโอยาวกว่าCSV600.020s ยังไม่ตรวจframe synchronization จึงไม่อ้างว่าframeแรกตรงเวลา0ของCSV คลิป167.05sเดิมในโฟลเดอร์แม่เป็นคนละรอบ
