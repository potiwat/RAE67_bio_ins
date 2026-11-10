> ชุด local นี้เก็บวิดีโอต้นฉบับไว้ใน `3-results/evidence/`; ยังไม่ได้อัปโหลด GitHub

# Week07 LeLamp ชุดส่งงานฉบับ 6 พฤศจิกายน 2026

เปิด3ไฟล์หลัก — ใช้ Word ฉบับที่ผู้ใช้แก้ไขและส่งล่าสุดจาก Desktop คัดลอกตรงต้นฉบับโดยไม่แก้เนื้อหา/ฟอนต์/รูปแบบ:

1. [ใบงาน Word](1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx) หรือ [Markdown](1-docs/markdown/worksheet.md)
2. [Proposal Word](1-docs/lab_documents/Lab07_Proposal_Group7.docx) และ [PDF](1-docs/lab_documents/Lab07_Proposal_Group7.pdf)
3. [รายงานผลฉบับผู้ใช้แก้ไขล่าสุด](1-docs/lab_documents/Lab07_Report_Group7.docx)

[ตรวจตามข้อกำหนดLab07](1-docs/checks/submission_audit_20261106_th.md) • [ผลsoftwarechecks](3-results/final_submission_checks_20261106/results.json) • [รายการWordทุกไฟล์](1-docs/markdown/word_files_index_th.md)

## ข้อมูลที่แนบ

- [AHM real6trials](3-results/real_robot_final/SIX_TRIAL_REPORT_TH.md) และ [simulation6trials](3-results/simulation_final/summary.json)
- [Teacher completedpolicy/transport/ROS3roles](3-results/course_bridge_verified_20261026_27/RECOVERY_AUDIT.json)
- [LivePi→WSL60s934rows](3-results/live_wsl_20261106/TECHNICAL_STATUS.json)
- [คลิปเล่นและCSV](3-results/evidence/VIDEO_INDEX.md)
- [13topiccontract](4-figures/topic_contract_13.json), [Draw.io](4-figures/lelamp_architecture.drawio), [sourceกราฟ3roles](4-figures/course_three_roles_source.json)

แยก C0/C1 transport ideal/delaydrop จาก AHM R=S/H และNormalpilotคนละรุ่น ผลCPGo1ไม่ใช่หลักฐานphysicalsmoothness มีN/A/hold/ordereffectตามจริง ROSอยู่WSLเชื่อมPiแบบlive; PiคุมUARTเอง Pi 5 ควบคุมโคมโดยตรง ส่วน WSL รับข้อมูลผ่าน SSH ไม่มี MCU แยกหรือ micro-ROS Agent

มีเฉพาะ Word Final 3 ไฟล์ในชุดส่ง ต้นฉบับและ Word เวอร์ชันเก่าย้ายออกแล้ว; raw pilot/failedattempts ที่เป็นหลักฐานการทดลองยังคงไว้ตามจริง ไม่ใช้แทน final trials

ตรวจไฟล์ด้วย `python verify_package.py` และทดสอบแบบmockด้วย `python run_pc_checks.py` ไม่เปิดฮาร์ดแวร์ ใช้completedpolicyผ่าน `python check_submission.py --policy-file completed_policy.py --contract group` ใน2-src/Lab07; student_policy.pyเก็บเป็นstarterต้นฉบับ

ยังไม่ได้อัปGitHub/ส่งให้อาจารย์ ไฟล์ในเครื่องเป็นชุดพร้อมนำส่ง ไม่ใช่การรับรองคะแนนหรือการอนุมัติโดยผู้สอน


## หลักฐานเพิ่มเติม: เล่นกับคน10นาที

[CSVของคลิปเล่นกับคน10นาที C1](3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md) เก็บจริง600.02s/7,098snapshots ครบ13topics แยกจากcontrolled C0/C1เดิม; แนบวิดีโอรอบนี้แล้วในโฟลเดอร์เดียวกับCSV ยังไม่ตรวจframe synchronization ไม่เปลี่ยนWordทั้ง3ไฟล์

## ตำแหน่งรูปวงจร วิดีโอ และ CSV

เปิด [รายการตำแหน่งไฟล์](1-docs/markdown/file_locations_th.md) เพื่อหารูปวงจรฉบับผู้ใช้ใน04_Design และวิดีโอ10นาทีพร้อมCSVใน07_Evidence รูปคัดลอกตรงต้นฉบับ ไม่แก้Wordทั้ง3ไฟล์

## การจัดหมวดเอกสารตาม repository

เอกสารหลักรวมใน `1-docs`: [รายงาน](1-docs/lab_documents/Lab07_Report_Group7.docx), [ข้อเสนอ](1-docs/lab_documents/Lab07_Proposal_Group7.docx), [ใบงาน Word](1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx), [ใบงาน Markdown](1-docs/markdown/worksheet.md)

`2-src` เก็บ source code; `3-results` เก็บข้อมูลและหลักฐานราย run; `4-figures` เก็บรูปและแผนภาพ ดู [รายงานจัดไฟล์](1-docs/checks/organization_report_th.md) และ [mapping](1-docs/checks/file_mapping.json) สำเนาต้นฉบับอยู่ `_originals_20261106` ไม่ใช่ชุดสำหรับอัปโหลด
