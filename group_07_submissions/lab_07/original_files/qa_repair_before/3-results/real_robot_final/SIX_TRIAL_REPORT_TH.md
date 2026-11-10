# Real robot C0/C1: เก็บครบ 6 รอบ

C0/C1 อย่างละ3รอบ รอบละ600วินาที ใช้scripted input ตารางเดียวกันและค่าเริ่มต้นH/CPGตรงกันในแต่ละคู่ ไม่ใช่การทดลองกดinputจริงโดยมนุษย์

| คู่ | เงื่อนไข | วินาที | แถว | Topics | พัก ToF | clean |
|---|---|---:|---:|---:|---:|---|
| P1 | C0 | 600.381 | 7642 | 13 | 1 | False |
| P1 | C1 | 600.417 | 7716 | 13 | 0 | True |
| P2 | C0 | 600.324 | 7659 | 13 | 0 | True |
| P2 | C1 | 600.354 | 7652 | 13 | 3 | False |
| P3 | C0 | 600.380 | 7667 | 13 | 0 | True |
| P3 | C1 | 600.382 | 7717 | 13 | 1 | False |

รวม 46,053 แถว ไม่มีwriter drop/error ตรวจSHA256ต้นฉบับตรงกันทุกรอบและCSVครบ13topics
มีพักToFสั้นรวม5ครั้ง รวม0.456วินาที เก็บไว้ตามจริง clean_complete=false ในรอบที่มีhold แต่capture_complete=true แสดงว่าเก็บครบเวลาและไม่เสียข้อมูล

ข้อมูลรายรอบอยู่ในโฟลเดอร์P1/P2/P3_C0/C1 แต่ละชุดมีraw trace.jsonl, metadata.json, summary.json, AUDIT.json, CSV_EXPORT_AUDIT.json, ROS13_MESSAGES.csv, TOPIC_COUNTS.csv และ OBSERVED_O1_METRICS.json

S/H/phiที่สังเกตในtraceตรงกับแบบอ้างอิงที่schedule indexเดียวกันทุกรอบ ข้อนี้ยืนยันการเชื่อมmodulation ไม่ใช่หลักฐานว่าC1เคลื่อนสมูทกว่าC0

OBSERVED_O1_METRICS_36_ROWS.csv แยก6อารมณ์x6รอบ คำนวณจากo1ช่วงต่อเนื่องเท่านั้น ค่าN/Aคือคาบไม่พอ โดยเฉพาะInterested/Angry ห้ามเติมจากsimulationหรือเชื่อมคาบข้ามอารมณ์ การเก็บครบ6รอบไม่เท่ากับพิสูจน์สมมติฐานครบทุกmetric

ROSbagเป็นreplay telemetryบนคอม ไม่ได้สั่งactuatorผ่านROS ตรวจreadbackทุกtopicแยกจากcapture quality ในverification.json ของแต่ละbag รอบที่sourceมีholdยังคงสถานะINCOMPLETEตามเกณฑ์cleanเดิม ไม่เปลี่ยนrawเพื่อให้PASS

เก็บรอบv1ที่ยกเลิกไว้แยก ไม่นับแทน6รอบนี้ งานวิเคราะห์ผลและจัดรายงานส่งอาจารย์ทำต่อบนคอมได้ ไม่ต้องเปิดhardwareเพื่อสำรองข้อมูลชุดนี้อีก

ตรวจROSbagreadbackครบทั้ง6ชุด: ทุกชุดพบ13topicsและcounts/decoded-fields hashตรงกับที่publish บางชุดระบุINCOMPLETEเนื่องจากsourceมีholdตามเกณฑ์cleanเดิม ไม่ใช่topicหาย ดูSIX_ROSBAG_AUDIT.json
