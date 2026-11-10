# รายงานแก้การจำแนกเอกสาร Lab07

อ้างอิง repository จริงบนเครื่อง C:/Users/USER/Desktop/BioInspired-Robotics-Labs: Lab04 และ Lab05 ใช้ 1-docs/LabXX_Report_Group7.docx, Lab06 มี 1-docs/Lab06_Report_Group7.pdf; worksheet.md อยู่ 1-docs; source/data/figures แยกเป็น 2-src/3-results/4-figures ไม่แก้ repository ต้นแบบ ซึ่งก่อนตรวจมี untracked extra/ อยู่แล้ว

## ก่อน → หลัง

- 01_Proposal/Week07_Proposal_Current_TH.docx → 1-docs/lab_documents/Lab07_Proposal_Group7.docx
- 01_Proposal/Week07_Proposal_Current_TH.pdf → 1-docs/lab_documents/Lab07_Proposal_Group7.pdf
- 03_Results/final_summary/Week07_Results_Summary_20261105.docx → 1-docs/lab_documents/Lab07_Report_Group7.docx
- 05_Worksheet/Week07_Worksheet_FINAL_RESULTS_20261105.docx → 1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx
- 05_Worksheet/worksheet.md → 1-docs/markdown/worksheet.md
- 03_Results/real_robot_pilot/PAIR_P2_S_H_PHI.pdf → 3-results/real_robot_pilot/PAIR_P2_S_H_PHI.pdf
- เอกสาร references, คู่มือ Markdown จาก design และบันทึกเอกสาร root รวมเข้า 1-docs
- 02_Source → 2-src, 03_Results → 3-results, 04_Design → 4-figures, 07_Evidence → 3-results/evidence

อ่านเนื้อหา Word ทั้ง 3 เพื่อจำแนกรายงาน/ข้อเสนอ/ใบงานจริง ชื่อ Proposal และ Student_Worksheet เป็นชื่อที่เลือกให้สอดคล้องกับ Lab07 และหน้าที่ ไม่อ้างว่าเป็นชื่อที่มีอยู่แล้วใน Lab เก่า และไม่เรียกใบงานที่นักศึกษากรอกแล้วว่า Student_Manual

## โครงสร้างปัจจุบัน

```text
Week_07_Lab_07_PREPARED_20261105/
  README.md
  1-docs/
    Lab07_Report_Group7.docx
    Lab07_Proposal_Group7.docx
    Lab07_Proposal_Group7.pdf
    Lab07_Student_Worksheet_TH.docx
    worksheet.md
    เอกสารอ้างอิง/คู่มือ/บันทึกและรายการตรวจ
  2-src/                 โค้ดเดิมและ ROS2 package
  3-results/             raw/config/results/log/evidence แยกตาม run
  4-figures/             ภาพ แผนภาพ และไฟล์ออกแบบ
  _originals_20261106/    สำเนาต้นฉบับครบก่อนแก้ ไม่ใช่ส่วนสำหรับอัป GitHub
  manifest_sha256.json
  verify_package.py
  run_pc_checks.py
```

README ของ package, report ที่เกิดจาก run, logs และ source snapshot ที่เป็นส่วนหนึ่งของชุดผลทดลอง คงไว้กับ run เช่นเดียวกับ Lab05 ที่เก็บ SOURCES.md ใน source_snapshot ไม่ย้ายประวัติการทดลองออกจาก data bundle

## การเปลี่ยนแปลงและความครบถ้วน

รายการไฟล์ก่อน/หลังครบทุกไฟล์อยู่ file_mapping.json (866 ไฟล์) พร้อม SHA256 ต้นฉบับและขนาด สำเนาต้นฉบับตรวจ checksum ครบใน _originals_20261106 ไม่ลบไฟล์ต้นฉบับ ไม่มีไฟล์ถูกข้าม รวมวิดีโอไว้ด้วย ไม่มีการสร้าง PDF หรือแก้เนื้อหา/รูปแบบ Word/PDF

แก้ Markdown links และ path ในเอกสาร/metadata/code ที่ใช้โครงสร้างเดิม; verify_package.py ใช้ manifest ใหม่และ UTF-8; run_pc_checks.py ใช้ 2-src; .gitignore ยกเว้น backup รายการไฟล์ข้อความที่แก้อยู่ organization_validation.json เก็บ source snapshots และ raw/result files เดิมไม่เปลี่ยน bytes ชื่อเดิมของ raw/config/snapshot คงไว้เพื่อรักษา dependency และ checksum ส่วนชื่อเอกสารหลักใช้ Lab07_* ตาม convention ของ repository แทนการบังคับ lowercase

## ผลทดสอบรอบนี้

- Python syntax ผ่าน 203 ไฟล์
- Mock tests ผ่าน 119 tests ดู organization_mock.log
- Policy ผ่านครบ 40 transition pairs, failures=0 ดู organization_policy.log
- ต้นฉบับใน backup ตรวจ SHA256 ครบ 866 ไฟล์ และทุกไฟล์มีปลายทางในชุดปัจจุบัน
- ตรวจ main document links ใน README, worksheet และ Word index
- verify_package.py ตรวจ manifest ทั้งชุดและ pilot snapshot (ผลคำสั่งตรวจท้ายงาน)

ยังไม่ได้ build/run ROS2 หรือเปิด hardware จริง ไม่มีการอ้างว่าหุ่นยนต์ทำงานผ่านจากการจัดไฟล์ ไม่สร้าง resource marker เพิ่มในรอบแก้การจัดหมวดนี้: setup.py เดิมอ้าง resource/lamp_week07 ซึ่งไม่มีในต้นฉบับ ต้องแก้ก่อน build ROS2

## ข้อจำกัด

วิดีโอ .MOV ขนาด 616 MB ยังอยู่ใน evidence และ backup ไม่อัป GitHub แบบไฟล์ปกติ ต้องเลือก LFS/hosting หากต้องการเผยแพร่ ไม่มี commit/push เอกสาร Word และ source snapshots อาจมีข้อความ path เก่าภายในซึ่งคงไว้ตามต้นฉบับ ไฟล์ผลทดลอง/history ที่มีชื่อและ hash อ้างอิงกันยังคงรูปเดิม ต้องตรวจแยกหากต้องการเปลี่ยนชื่อภายในทั้งหมด การแก้ครั้งนี้เน้นหมวดเอกสาร ชื่อเอกสาร และจุดใช้งานที่ปรับแล้วตามรายการ

## แยกหมวดภายใน 1-docs เพิ่มเติม

เอกสาร Word/PDF อยู่ lab_documents; ใบงานและคู่มือ Markdown อยู่ markdown; อ้างอิงอยู่ references; ข้อมูลที่มาอยู่ metadata; ผลตรวจอยู่ checks ดู ../README.md และ docs_reorganization.json สำหรับตำแหน่งล่าสุด ไฟล์เอกสารทั้ง 34 ไฟล์ตรวจนับครบ เนื้อหา Word/PDF ไม่เปลี่ยน และตรวจลิงก์หน้าหลัก/worksheet/index/ตำแหน่งไฟล์ผ่าน
