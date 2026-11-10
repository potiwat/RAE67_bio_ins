> ZIP ฉบับส่งต่อ: ไม่รวมวิดีโอ10นาทีตามคำขอ อ่าน [วิธีใส่คลิปภายหลัง](VIDEO_NOT_INCLUDED_TH.md) CSVและไฟล์อื่นยังครบ

# Week07 LeLamp ชุดส่งงานฉบับ 6 พฤศจิกายน 2026

เปิด3ไฟล์หลัก — ใช้ Word ฉบับที่ผู้ใช้แก้ไขและส่งล่าสุดจาก Desktop คัดลอกตรงต้นฉบับโดยไม่แก้เนื้อหา/ฟอนต์/รูปแบบ:

1. [ใบงาน Word](05_Worksheet/Week07_Worksheet_FINAL_RESULTS_20261105.docx) หรือ [Markdown](05_Worksheet/worksheet.md)
2. [Proposal Word](01_Proposal/Week07_Proposal_Current_TH.docx) และ [PDF](01_Proposal/Week07_Proposal_Current_TH.pdf)
3. [รายงานผลฉบับผู้ใช้แก้ไขล่าสุด](03_Results/final_summary/Week07_Results_Summary_20261105.docx)

[ตรวจตามข้อกำหนดLab07](SUBMISSION_AUDIT_20261106_TH.md) • [ผลsoftwarechecks](03_Results/final_submission_checks_20261106/results.json) • [รายการWordทุกไฟล์](WORD_FILES_INDEX_TH.md)

## ข้อมูลที่แนบ

- [AHM real6trials](03_Results/real_robot_final/SIX_TRIAL_REPORT_TH.md) และ [simulation6trials](03_Results/simulation_final/summary.json)
- [Teacher completedpolicy/transport/ROS3roles](03_Results/course_bridge_verified_20261026_27/RECOVERY_AUDIT.json)
- [LivePi→WSL60s934rows](03_Results/live_wsl_20261106/TECHNICAL_STATUS.json)
- [คลิปเล่นและCSV](07_Evidence/VIDEO_INDEX.md)
- [13topiccontract](04_Design/TOPIC_CONTRACT_13.json), [Draw.io](04_Design/LeLamp_Architecture.drawio), [sourceกราฟ3roles](04_Design/COURSE_THREE_ROLES_SOURCE.json)

แยก C0/C1 transport ideal/delaydrop จาก AHM R=S/H และNormalpilotคนละรุ่น ผลCPGo1ไม่ใช่หลักฐานphysicalsmoothness มีN/A/hold/ordereffectตามจริง ROSอยู่WSLเชื่อมPiแบบlive; PiคุมUARTเอง Pi 5 ควบคุมโคมโดยตรง ส่วน WSL รับข้อมูลผ่าน SSH ไม่มี MCU แยกหรือ micro-ROS Agent

มีเฉพาะ Word Final 3 ไฟล์ในชุดส่ง ต้นฉบับและ Word เวอร์ชันเก่าย้ายออกแล้ว; raw pilot/failedattempts ที่เป็นหลักฐานการทดลองยังคงไว้ตามจริง ไม่ใช้แทน final trials

ตรวจไฟล์ด้วย `python verify_package.py` และทดสอบแบบmockด้วย `python run_pc_checks.py` ไม่เปิดฮาร์ดแวร์ ใช้completedpolicyผ่าน `python check_submission.py --policy-file completed_policy.py --contract group` ใน02_Source/Lab07; student_policy.pyเก็บเป็นstarterต้นฉบับ

ยังไม่ได้อัปGitHub/ส่งให้อาจารย์ ไฟล์ในเครื่องเป็นชุดพร้อมนำส่ง ไม่ใช่การรับรองคะแนนหรือการอนุมัติโดยผู้สอน


## หลักฐานเพิ่มเติม: เล่นกับคน10นาที

[CSVของคลิปเล่นกับคน10นาที C1](07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md) เก็บจริง600.02s/7,098snapshots ครบ13topics แยกจากcontrolled C0/C1เดิม; แนบวิดีโอรอบนี้แล้วในโฟลเดอร์เดียวกับCSV ยังไม่ตรวจframe synchronization ไม่เปลี่ยนWordทั้ง3ไฟล์

## ตำแหน่งรูปวงจร วิดีโอ และ CSV

เปิด [รายการตำแหน่งไฟล์](FILE_LOCATIONS_TH.md) เพื่อหารูปวงจรฉบับผู้ใช้ใน04_Design และวิดีโอ10นาทีพร้อมCSVใน07_Evidence รูปคัดลอกตรงต้นฉบับ ไม่แก้Wordทั้ง3ไฟล์
