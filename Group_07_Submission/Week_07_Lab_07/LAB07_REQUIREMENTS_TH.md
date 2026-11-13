# ตรวจชุดส่งกับข้อกำหนด Lab 07 ของอาจารย์

ตรวจวันที่ 12 พฤศจิกายน 2569 จาก [หัวข้องานส่ง Week07](https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_07/README.md#L140-L145), [ใบงานต้นฉบับ](https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_07/Week07_Student_Worksheet_TH.docx) และ [รายการที่นักศึกษาต้องตอบ](https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_07/worksheet.md) ที่ commit `fa528b169f1127ee3e0e9fae3d721546bf1b82d2`

| รายการตามโจทย์ | ผลตรวจของกลุ่ม | เปิดหลักฐาน |
|---|---|---|
| 1. ผังสามบทบาท หัวข้อ ชนิด หน่วย QoS และขอบเขตเวลา | มีผังสามโหนดของแบบฝึกพร้อมหลักฐานค้นพบจริง และมีผังแยกสำหรับ Raspberry Pi 5 ที่ใช้กับหุ่นจริง **ข้อที่ต่างจากโจทย์คือส่วนขยายที่ระบุในข้อ 1** กลุ่มเลือกส่งสถาปัตยกรรม Pi 5 ที่สร้างจริงและไม่มีแผนเพิ่มฮาร์ดแวร์ส่วนนั้น การรับงานรูปแบบนี้ขึ้นกับอาจารย์ | [ผัง Pi 5](04_Design/Lamp_data_flow.png) · [สามโหนดของแบบฝึก](04_Design/ROS_bridge_roles.png) · [สัญญาเจ็ดหัวข้อ](04_Design/interface_contract.json) · [รายการ endpoints ที่พบ](03_Results/course_ros/observed_endpoints.csv) |
| 2. นโยบายของกลุ่มผ่าน bridge สองเงื่อนไข เงื่อนไขละสามครั้ง เก็บ config, traces, ผลและ misses | ใช้ตัวตรวจ group ของอาจารย์ผ่าน 40/40 คู่สถานะ–เหตุการณ์ รัน bridge ใหม่หกรอบที่ seeds 41/42/43 ด้วยนโยบายเดียวกัน เจ็ดอินพุตหลักต่อ seed รวม 21 ต่อเงื่อนไข ideal พบคำสั่งเคลื่อนและสีภายในหนึ่งวินาที 21/21 ส่วน stressed พบ 19/21 คงสองรายการที่ขาดไว้ในตัวหาร Replay seed 42 ได้ไฟล์ input, command และ events ตรงกันทุกไบต์ | [วิธีรัน](03_Results/course_bridge/README_TH.md) · [ผลรายคู่](03_Results/course_bridge/transport_summary.csv) · [ผลรายอินพุต](03_Results/course_bridge/primary_outcomes.csv) · [ผลการตรวจ](03_Results/course_bridge/verification.json) |
| 3. proposal.json และ Proposal 2–3 หน้า มีแรงบันดาลใจ AHM–SO(2) CPG, baseline, metrics, repeats, simulation, หุ่นจริง, การสาธิต, controls, calibration, safety และ timeline | Proposal ฉบับจัดหน้าล่าสุดมี 4 หน้า เกินข้อกำหนด 2–3 หน้าอยู่ 1 หน้า ส่วน JSON ผ่านตัวตรวจอย่างเป็นทางการ แบบจำลองตัวควบคุมและหุ่นจริงใช้ C0/C1 สามคู่ เงื่อนไขละ 180 วินาที ตัวชี้วัดหลัก M1/M2 แสดงจำนวนคาบที่ใช้ได้จริง คลิปเล่นกับผู้ใช้ยาว 632.180 วินาที ข้อมูลมอเตอร์ครอบคลุม 631.926 วินาที | [Proposal PDF](01_Proposal/Week07_Proposal_Current_TH.pdf) · [proposal.json](01_Proposal/proposal.json) · [ผลตรวจ](01_Proposal/PROPOSAL_CHECK.txt) · [ใบงาน](05_Worksheet/Week07_Worksheet_TH.docx) · [ผลจำลอง](03_Results/simulation/README_TH.md) · [หกรอบหุ่นจริง](03_Results/real_robot/summary/Run_index.csv) · [คลิป](07_Evidence/present/README_TH.md) |
| 4. แสดงขอบเขตของแบบฝึก 22 วินาทีและแยกหลักฐานโครงงาน | แบบฝึก 22 วินาทีเปรียบเทียบการส่งข้อมูลในเวลาเสมือน ส่วนงานวิจัย 180 วินาทีเปรียบเทียบ R=S กับ R=H การเล่นสาธิตมีคลิปและ CSV ของตนเอง | [ผลการทดลองและดัชนี](03_Results/README_TH.md) · [CSV รอบสาธิต](07_Evidence/present/present_feedback.csv) |

## ขอบเขตของหลักฐานเกี่ยวกับเวลาและ topics

แบบฝึก ROS 2 รันในเครื่องคอมพิวเตอร์ เก็บ rosbag จริงได้ **7 หัวข้อ 7,425 ข้อความ** และอ่านข้อความ CDR กลับครบทุกข้อความ จำนวนที่ผู้ส่งบันทึก ผู้รับเห็น และ bag เก็บได้ต่างกัน จึงแสดงยอดแยกสามจุด อธิบายการแก้เฉพาะการเขียนอาร์เรย์ลง CSV ของตัวอย่าง Jazzy ไว้ในชุดหลักฐาน [ยอดข้อความจริง](03_Results/course_ros/message_counts.csv) · [รายละเอียดการรัน ROS 2](03_Results/course_ros/README_TH.md)

กลุ่มออกแบบสัญญาของโคม **13 หัวข้อ** โดยเพิ่มสถานะอินพุต, AHM/CPG, ข้อต่อ, การติดตามหน้า, การวินิจฉัย และ trace หุ่นจริงบันทึกไฟล์ native โดยตรง สามารถจัดกลุ่มค่าหลายส่วนลง CSV ย้อนหลังได้ ในหกรอบไม่มีลำดับกรอบหน้ารายเฟรมตลอดช่วงวัด และข้อมูลปุ่ม/สัมผัสทางกายภาพมีขอบเขตต่างจากระดับสิ่งเร้าตามตาราง จึงไม่ระบุว่าเก็บ rosbag 13 หัวข้อครบในหกรอบนั้น [สัญญา 13 หัวข้อ](04_Design/TOPIC_CONTRACT_13.json) · [หลักฐานที่มีจริงรายหัวข้อ](04_Design/TOPIC_COVERAGE.csv)

คาบการส่ายฐานใช้ encoder ส่วนเวลาเคลื่อนไหวและสีในแบบฝึกอ้างอิงคำสั่งบนเวลาเสมือน เวลาเฟรมแรกของคลิปกับเวลาแรกของ feedback ยังไม่มีการซิงก์ระดับเฟรม เกณฑ์ความหน่วงถึงการขยับจริงและแสงจริงจึงต้องมีหลักฐานเพิ่มเติมหากนำไปอ้าง

เรียกตัวตรวจของอาจารย์จากรากโฟลเดอร์นี้ได้ด้วย

```console
python 01_Proposal/check_proposal.py 01_Proposal/proposal.json
python 03_Results/course_bridge/runtime/check_submission.py --policy-file 03_Results/course_bridge/runtime/completed_policy.py --contract group
```

รุ่นของไฟล์ตรวจใช้ SHA จาก [บัญชีแหล่งต้นทาง](06_References/TEACHER_LAB07_SOURCE.json)

