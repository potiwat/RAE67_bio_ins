ชุดส่งงาน RAE67 Lab 02–07 (จัดจาก ZIP โปรเจกต์ที่ผู้ใช้แนบ)

ไฟล์หลักที่เพิ่มในแต่ละ lab_xx:
- *_Answered.docx: ใบงาน Word จากต้นฉบับที่กรอกข้อมูลคำตอบและตารางแล้ว
- Student_Report.docx: รายงานผลทดลองจาก student_report.md และหลักฐานจำลอง
- lab_07/Student_Proposal_Short.docx: ข้อเสนอโครงงาน 2 หน้า (เหมาะกับโจทย์ 2–3 หน้า)
- lab_07/Student_Proposal_Full.docx: ข้อเสนอเชิงรายละเอียด 4 หน้า
- submission_evidence/: สำเนาข้อมูลผลทดลองจริงจาก worktree ที่มีใน ZIP (metrics/config/raw CSV/manifest/replay)

คำเตือน: ผล Lab 02–07 เป็น simulator/offline model; Lab 07 ยังไม่ได้ทดสอบบน ROS 2/hardware/ผู้เข้าร่วมจริง
ชื่อและรหัสที่ใช้ตามรายงานต้นทาง: ภาณุพร มาศรี / 6752500118 ต้องตรวจให้ตรงผู้ส่ง
ต้นฉบับ DOCX เดิมไม่ถูกเขียนทับ

นำงานเข้า repo (PowerShell Windows):
1) ดาวน์โหลด ZIP ชุดเต็ม แล้วแตก ZIP ไปที่ D:\gitt\RAE67_bio_ins (Merge folders)
2) cd D:\gitt\RAE67_bio_ins
3) git status --short
4) git add lab_02 lab_03 lab_04 lab_05 lab_06 lab_07 README_TH.txt
5) git commit -m "Add completed Lab 02-07 worksheets reports and evidence"
6) git push -u origin student-work
7) หากอาจารย์กำหนดให้ส่ง Pull Request: เปิด https://github.com/potiwat/RAE67_bio_ins/compare แล้วตรวจว่า base=potiwat/main และ head=doubible/student-work จากนั้น Create pull request
8) ส่งลิงก์ Pull Request ให้ผู้สอน หรือส่งลิงก์ Branch ตามข้อกำหนดอาจารย์

ตรวจสอบความพร้อมก่อน submit: git status; เปิด DOCX; ยืนยันชื่อนักศึกษาและวันส่ง; ยืนยันกราฟและไฟล์ CSV. อย่าลบ worktree ต้นทางจนกว่าจะตรวจงานครบ
