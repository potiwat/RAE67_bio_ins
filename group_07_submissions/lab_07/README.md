## วิดีโอหลักฐานการทดลอง Lab07 — สถานะ GitHub ปัจจุบัน

ไฟล์วิดีโอจริงทั้งสองอยู่ใน [GitHub Releases](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/tag/lab07-video-evidence) ไม่ได้แนบอยู่ใน Git Tree ของ `3-results/evidence` ดาวน์โหลด [คลิปทดลองเล่น — default.mp4](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/default.mp4) และ [คลิปเล่นกับคน 10 นาที — _10._C1.MOV](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) ได้โดยตรง

CSV และข้อมูลการทดลองอยู่ใน [3-results/evidence](3-results/evidence/) ตามเดิม ชื่อไฟล์บน Release ต่างจากชื่อไฟล์ต้นฉบับ แต่ SHA-256 ตรงกับค่าต้นฉบับที่ระบุไว้ ดู [ดัชนีวิดีโอพร้อมลิงก์ CSV ขนาด และ SHA-256](3-results/evidence/VIDEO_INDEX.md)

วิดีโอทั้งสองเป็นหลักฐานการทดลองคนละรอบ ยังไม่ได้ยืนยันการ Synchronize Frame กับ CSV แบบ Frame-by-frame และไม่ถือว่าเฟรมแรกตรงกับเวลา 0 ของ CSV โดยอัตโนมัติ ข้อความสถานะชุด local/ZIP เดิมด้านล่างเป็นประวัติการเตรียมชุดงาน

> ผลตรวจล่าสุด: เพิ่ม `2-src/calibration_readonly/read_only_bus.py` จากไฟล์ที่ผู้ใช้ส่งแล้ว ตรวจ syntax และ mock transport/baseline ผ่าน 25 tests; ยังไม่ได้ build ROS2/Pi หรือรันฮาร์ดแวร์จริง ดู [รายงาน QA](1-docs/checks/qa_report_th.md)

> ประวัติชุด local: เคยเก็บวิดีโอต้นฉบับใน `3-results/evidence/` และยังไม่ได้อัปโหลด ณ เวลาจัดชุดนั้น ปัจจุบันดาวน์โหลดวิดีโอจริงจาก GitHub Releases ตามหัวข้อด้านบน

# Week07 LeLamp ชุดส่งงานฉบับ 6 พฤศจิกายน 2026

เปิด3ไฟล์หลัก — ใช้ Word ฉบับที่ผู้ใช้แก้ไขและส่งล่าสุดจาก Desktop คัดลอกตรงต้นฉบับโดยไม่แก้เนื้อหา/ฟอนต์/รูปแบบ:

1. [ใบงาน Word](1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx) หรือ [Markdown](1-docs/markdown/worksheet.md)
2. [Proposal Word](1-docs/lab_documents/Lab07_Proposal_Group7.docx) (ไม่มีฉบับ PDF ใน Git Tree ของชุดนี้)
3. [รายงานผลฉบับผู้ใช้แก้ไขล่าสุด](1-docs/lab_documents/Lab07_Report_Group7.docx)

[ตรวจตามข้อกำหนดLab07](1-docs/checks/submission_audit_20261106_th.md) • [ผลsoftwarechecks](3-results/final_submission_checks_20261106/results.json) • [รายการWordทุกไฟล์](1-docs/markdown/word_files_index_th.md)

## ข้อมูลที่แนบ

- [AHM real6trials](1-docs/markdown/six_trial_report_th.md) และ [simulation6trials](3-results/simulation_final/summary.json)
- [Teacher completedpolicy/transport/ROS3roles](3-results/course_bridge_verified_20261026_27/RECOVERY_AUDIT.json)
- [LivePi→WSL60s934rows](3-results/live_wsl_20261106/TECHNICAL_STATUS.json)
- [คลิปเล่นและCSV](3-results/evidence/VIDEO_INDEX.md)
- [13topiccontract](2-src/ros2_package/config/topic_contract_13.json), [Draw.io](4-figures/lelamp_architecture.drawio), [sourceกราฟ3roles](4-figures/course_three_roles_source.json)

แยก C0/C1 transport ideal/delaydrop จาก AHM R=S/H และNormalpilotคนละรุ่น ผลCPGo1ไม่ใช่หลักฐานphysicalsmoothness มีN/A/hold/ordereffectตามจริง ROSอยู่WSLเชื่อมPiแบบlive; PiคุมUARTเอง Pi 5 ควบคุมโคมโดยตรง ส่วน WSL รับข้อมูลผ่าน SSH ไม่มี MCU แยกหรือ micro-ROS Agent

มีเฉพาะ Word Final 3 ไฟล์ในชุดส่ง ต้นฉบับและ Word เวอร์ชันเก่าย้ายออกแล้ว; raw pilot/failedattempts ที่เป็นหลักฐานการทดลองยังคงไว้ตามจริง ไม่ใช้แทน final trials

ตรวจไฟล์ด้วย `python verify_package.py` และทดสอบแบบmockด้วย `python run_pc_checks.py` ไม่เปิดฮาร์ดแวร์ ใช้completedpolicyผ่าน `python check_submission.py --policy-file completed_policy.py --contract group` ใน2-src/ros2_package; student_policy.pyเก็บเป็นstarterต้นฉบับ

ประวัติสถานะก่อนเผยแพร่: ชุดในเครื่องเคยระบุว่ายังไม่ได้อัป GitHub/ส่งให้อาจารย์ ปัจจุบันสำเนางานอยู่ใน Fork และวิดีโออยู่ใน Releases แล้ว การเผยแพร่นี้ไม่ใช่การรับรองคะแนน การอนุมัติโดยผู้สอน หรือหลักฐานยืนยันเวลาส่งถึงผู้สอน


## หลักฐานเพิ่มเติม: เล่นกับคน10นาที

[CSVของคลิปเล่นกับคน10นาที C1](3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md) เก็บจริง600.02s/7,098snapshots ครบ13topics แยกจากcontrolled C0/C1เดิม; วิดีโอรอบนี้เผยแพร่ใน GitHub Releases ส่วน CSV อยู่ในโฟลเดอร์หลักฐานตามเดิม ยังไม่ตรวจframe synchronization ไม่เปลี่ยนWordทั้ง3ไฟล์

## ตำแหน่งรูปวงจร วิดีโอ และ CSV

เปิด [รายการตำแหน่งไฟล์](1-docs/markdown/file_locations_th.md) เพื่อหารูปวงจรใน `4-figures` และ CSV ใน `3-results/evidence` ส่วนไฟล์วิดีโอจริงอยู่ใน GitHub Releases รูปคัดลอกตรงต้นฉบับ ไม่แก้Wordทั้ง3ไฟล์

## การจัดหมวดเอกสารตาม repository

เอกสารหลักรวมใน `1-docs`: [รายงาน](1-docs/lab_documents/Lab07_Report_Group7.docx), [ข้อเสนอ](1-docs/lab_documents/Lab07_Proposal_Group7.docx), [ใบงาน Word](1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx), [ใบงาน Markdown](1-docs/markdown/worksheet.md)

`2-src` เก็บ source code; `3-results` เก็บข้อมูลและหลักฐานราย run; `4-figures` เก็บรูปและแผนภาพ ดู [รายงานจัดไฟล์](1-docs/checks/organization_report_th.md) และ [mapping](1-docs/checks/file_mapping.json) สำเนาต้นฉบับอยู่ `original_files` ไม่ใช่ชุดสำหรับอัปโหลด
