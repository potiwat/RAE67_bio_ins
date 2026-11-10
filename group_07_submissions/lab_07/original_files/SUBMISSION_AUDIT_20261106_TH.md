# Lab07 ข้อกำหนดและหลักฐานฉบับปิดชุดส่ง 6 พฤศจิกายน 2026

ตารางนี้อ้าง [README Lab07 ผู้สอน](06_References/teacher_lab07_README_submission_reference.md) หัวข้อ งานส่ง Week07 ไม่ใช้คำว่า checker ผ่านแทนการรับรองผลวิจัยหรือการให้คะแนน

| ข้อกำหนด | สิ่งที่แนบและสถานะจริง |
|---|---|
| 1 Graph / publisher-topic-subscriber / 3 roles / units-QoS / boundary | ใบงานมีภาพระบบที่ใช้จริง, ภาพสาม roles จาก endpoint discovery course ROS และ screenshot replay ของผู้ใช้; contract13topics/หน่วย/QoS/clock ชัดเจน |
| 1 ขอบเขต host และ MCU ที่ใช้จริง | กลุ่มใช้ Pi 5 ควบคุมโคมโดยตรง และ ROS บน WSL รับข้อมูลผ่าน SSH; ไม่มี MCU แยกหรือ micro-ROS Agent ไม่เสนอแผนเพิ่ม ESP32 ในนามกลุ่ม คงข้อความโจทย์ไว้และอธิบายระบบจริงแทน |
| 2 Completed policy ผ่าน bridge พร้อม traces/config/misses | completed_policy.py ผ่าน40/40; offline C0ideal/C1delay+drop 3pairedseeds41/42/43, expected C0=21/21,C1=19/21 พร้อมmisses2,raw/config/source snapshots/hash และ replay byte-identical |
| 2 ROSสาม roles รันจริง | เก็บ3รอบ synthetic source22sบนWSL/Jazzy: inputs→interaction→output_collectorพร้อมrecorder; มี5statesและreceipt-stale recovery เก็บความต่างจำนวนmessageในbagตามจริง ไม่อ้างว่าbagเก่าครบทุกmessage |
| 3 Proposal2–3หน้า + proposal.json | Proposal Word/PDF3หน้าและJSONอัปเดตจากงานจริง checkerผ่าน มีแหล่งสมการ AHM≥1,SO(2),integration,controls/parameters/metrics/3repeats/clock/safety/timeline ผู้รับผิดชอบร่วมตามแผน=กลุ่ม7 ไม่สร้างสัดส่วนผลงานรายบุคคล |
| 3 Simulation AND Realrobot / scenario600s | AHM simulation6trials และโคมจริง6trials/3คู่/600s ครบ raw/CSV/ROSbag13topics/config/SHA; โคมจริงใช้controlled scripted inputs โดยผู้ใช้นั่งหน้ากล้อง ไม่อ้างว่าคนกดทุกเหตุการณ์ด้วยมือ |
| 4 Offline22sไม่แทนโคม600s | แยกteachertransport, AHMsix-state, Normalpilotและliveverificationชัดเจน ไม่รวมC0/C1คนละความหมายหรือคนละรุ่น |

## ROS ที่ทำจริง

ระบบโคมใช้ Pi5/Python ควบคุม UART/LED เอง ROS2 Jazzyอยู่บนWSL รับsessionผ่านSSHแบบliveและpublish13topicsเข้าrosbag ไม่มีROSactuatorsubscriberบนPi รอบliveที่ผ่านมี934แถว/60.029s count/decodedhashตรงทุกtopic พร้อมหลักฐานว่าข้อมูลเพิ่มก่อนsourceจบ ไม่เรียกว่าROSควบคุมมอเตอร์หรือROSบนPi

มีผลcourse ROSสามrolesแยกจากliveobserver ไม่เอาdiagramfunctionalภายในPiมาเรียกว่าROSnodesจริง กลุ่มใช้ Pi 5 + WSL ตามระบบจริง ไม่ได้เสนอหรือทำ MCU/Agent extension และไม่อ้างว่าระบบนี้เป็น micro-ROS ความถูกต้องของแนวทางและคะแนนยังเป็นการพิจารณาของผู้สอน

## ข้อจำกัดที่คงไว้

AHMมี3realtrialsที่พบholdสั้นรวม5ครั้ง0.456s แยกcapture_complete/clean_complete; Interested/Angryคาบไม่พอให้N/A; Sleepyผลไม่สม่ำเสมอ; ไม่มีphysical motorfrequency/jerk/onset uncertaintyหรือสถิติยืนยันความสมูท Clip167.05sเป็นหลักฐานประกอบ ไม่พบข้อกำหนดให้คลิปยาว10นาที ลำดับC0→C1ทุกคู่ไม่ได้counterbalance

## ผลตรวจสุดท้ายและประวัติ

[Final checks](03_Results/final_submission_checks_20261106/results.json): completedpolicy,proposal,PCruntime,livebridgeผ่าน ผลFAILของstarter8/40และproposalก่อนเติมในsubmission_audit_20261106เป็นประวัติก่อนแก้/ก่อนกู้completedpolicy ไม่ใช่สถานะสุดท้าย

ตรวจรอบแรกพลาดที่ดูเฉพาะไฟล์staging: completedpolicy/bridge/ROSหลักฐานเดิมอยู่Lab07โปรเจกต์หลักและกู้เข้าชุดแล้ว ไม่ได้สร้างผลใหม่ทดแทน สำเนาextractใบงานLab04/05ที่อ้างassetsไม่ครบแยกเก็บนอกZIPเป็นประวัติ ไม่ใช่ไฟล์จำเป็นของLab07 ต้นฉบับและ Word เวอร์ชันเก่าย้ายออกจากชุดส่งแล้วตามคำสั่งผู้ใช้

ชุดนี้พร้อมตรวจและนำส่งในเครื่อง ยังไม่ได้อัปGitHubหรือส่งให้อาจารย์ ไม่มีการอ้างว่าได้รับอนุมัติหรือคะแนนผ่านแล้ว
