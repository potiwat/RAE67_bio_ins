# รายงานจัดเอกสาร Fork — 13 พฤศจิกายน 2569

## ตำแหน่งสำหรับส่งอาจารย์

ชุดใหม่อยู่ `group_07_submissions/lab_07/` ภายใน Fork; ไม่ได้เขียนทับ Lab07 ด้วยชุดเก่าจาก repository ส่วนตัว โฟลเดอร์ `lab_02`–`lab_07` ที่ root เป็นพื้นที่ของผู้สอนและไม่ได้แก้ในงานนี้

```text
group_07_submissions/lab_07/
  README.md
  1-docs/
    README.md
    lab_documents/
      Lab07_Report_Group7.docx
      Lab07_Student_Worksheet_TH.docx
      Lab07_Proposal_Group7.docx
      Lab07_Proposal_Group7.pdf
    markdown/
    references/
    metadata/
  2-src/
    analysis/
    hardware/
    proposal/
    config/
    reproduce.py
    requirements.txt
    README.md
  3-results/
    course_bridge/
    course_ros/
    real_robot/
    simulation/
    figures/
    evidence/
    coverage/
    software_checks/
    organization_qa_20261113/
  4-figures/
  manifest_sha256.json
  verify_package.py
```

แบบโครงสร้างอ้างอิง repository เก่าซึ่งใช้ 1-docs/2-src/3-results/4-figures แต่เนื้อหาที่จัดเป็นชุดทดลองใหม่วันที่ 12 พฤศจิกายน ไม่ใช้ผลวันที่ 6–7 พฤศจิกายนแทน ทุกชื่อ Word ใช้ convention Lab07_* ตามชุดเก่า; ชื่อ artifacts ของ run/source snapshots ยังคงเดิมเพื่อรักษา hashes และ dependency

## สิ่งที่แก้

- รวมรายงาน ใบงาน และ Proposal Word/PDF ไว้ 1-docs/lab_documents ไม่แก้ bytes ภายในเอกสาร
- แยก Markdown คู่มือ/ผลอธิบาย/โจทย์ไว้ 1-docs/markdown และแหล่งอ้างอิงไว้ references
- ย้าย proposal checker/config และ topic contracts ไป 2-src; ผล checker และตาราง coverage ไป 3-results
- คงโค้ด hardware ที่เป็นหลักฐาน source hash และข้อมูล raw ไว้ครบทั้งชุด ไม่แก้ค่าหรือประวัติการทดลอง
- ภาพสถาปัตยกรรม/วงจรอยู่ 4-figures; กราฟที่เป็นส่วนของชุดผลอยู่ 3-results/figures
- ปรับลิงก์และ path ในตัวตรวจ/analysis ให้ตรงโครงสร้างใหม่ โดยรักษา provenance csv_path ของผลเดิมไว้ และแปลงเฉพาะตอนเข้าถึงไฟล์
- แก้ README root และ group_07_submissions ให้ชี้เอกสารล่าสุดชัดเจน แยกประวัติ commit ของชุดเก่าจากวันที่ทดลองชุดใหม่

## การเก็บต้นฉบับ

สำเนาทั้งโฟลเดอร์ที่มีชุดเก่าและชุดใหม่ปนกัน 2,674 ไฟล์ เก็บครบที่ `local_backup_20261113/lab07_before/` ภายใน Fork มี Word ชุดใหม่ ชุดเก่า และ original_files เดิมทั้งหมด โฟลเดอร์ backup ถูก .gitignore เพื่อไม่เผลออัปโหลดข้อมูลซ้ำ; ไม่มีการลบเอกสาร/วิดีโอต้นฉบับ ไม่ลบ duplicates และไม่สร้าง PDF เพิ่ม

inventory ก่อนแก้ทั้ง repository มี 3,059 ไฟล์ ไม่รวม .git; ตรวจ SHA256 พบครบทุกไฟล์ในสำเนาที่เก็บหรือที่เดิม ทั้ง 4 ไฟล์ Word/PDF ปัจจุบันตรงกับชุดใหม่ทุกไบต์ (Word 3 ฉบับและ PDF 1 ฉบับ)

มีไฟล์จากชุดใหม่ 565 รายการที่จัดเข้าชุดปัจจุบัน อีก 2,109 รายการในโฟลเดอร์ที่เคยปนกันเป็นชุดเก่า/teacher scaffold และเก็บใน backup ไม่ผสมเป็นผลทดลองใหม่ ไฟล์อื่นใน repository อีก 385 รายการตรวจนับและรักษาไว้

ตารางทุกไฟล์ก่อน/หลังพร้อม SHA256: [reconciliation.csv](../3-results/organization_qa_20261113/reconciliation.csv) และ [JSON](../3-results/organization_qa_20261113/reconciliation.json)

## ผลตรวจ

- [PASS] ตรวจนับต้นฉบับ 3,059 ไฟล์ ไม่มี missing/change ที่ไม่ได้รักษาต้นฉบับไว้
- [PASS] เอกสาร Word/PDF หลัก 4 ไฟล์ตรง SHA256 เดิม
- [PASS] Lab02–Lab06 ที่ส่งไว้เทียบ repository เก่าครบ 309 ไฟล์ ตรงกันทุกไฟล์ จึงไม่แก้
- [PASS] Python syntax 259 ไฟล์
- [PASS] ลิงก์ Markdown ของเอกสารใช้งาน 14 ฉบับ ไม่มี broken links/case collisions (ก่อนเพิ่มรายงานฉบับนี้; หน้ารวมรายงานตรวจเพิ่มท้ายงาน)
- [PASS] ตัวตรวจการส่ง: Word 3 ฉบับ, 6 real runs, raw 21,464 แถว, parameter 21,458 samples, demo 64,212 แถว/631.926 s, official proposal/group policy checks, หลักฐาน ROS เดิม 7 topics และ native coverage 13 entries
- [PASS] native export --verify: CSV 6 รอบ, coverage 78 รายการและ crosswalk 13 รายการ ตรงกับผลที่แนบ
- [PASS] reproduce.py: อ่าน original files 111 ไฟล์และคำนวณตารางซ้ำ 33 ชุดตรงกับผลตามตัวเปรียบเทียบ โดย 31 ชุด byte-identical อีก 2 ชุดเทียบค่าตัวเลขตามโค้ดเดิม
- [LIMITATION] ภาพ PNG ที่คำนวณใหม่ทั้ง 3 ภาพไม่ตรงทุกไบต์จาก environment การเรนเดอร์ จึงไม่แทนที่ภาพเดิมและไม่อ้างว่าภาพตรง byte-for-byte
- [DECLARED SOURCE LIMITATION] manifest ของ hardware ตรวจได้ 237/240 entries มี guard files 3 รายการที่ต้นฉบับระบุ unavailable ไว้แล้ว ไม่ใช่หายระหว่างจัดเอกสาร
- [NOT TESTED] ไม่เปิด Pi/UART/GPIO/กล้อง ไม่รัน ROS2 ใหม่ ไม่ตรวจภาพเอกสารด้วยสายตาหรือซิงก์วิดีโอระดับเฟรม

ตัวตรวจที่ผ่านเป็นการอ่านข้อมูลจริงที่แนบมา ไม่ใช่การจำลองหรือสร้างผลทดลองแทน ผลเก่าที่ไม่เข้าเกณฑ์และข้อจำกัดยังอยู่ตามต้นฉบับ

## ข้อควรทราบของเอกสารใหม่

Proposal PDF ต้นฉบับใหม่มี 4 หน้า ขณะที่โจทย์ระบุ 2–3 หน้า ข้อจำกัดนี้มีระบุไว้ในเอกสารชุดใหม่แล้ว งานนี้จัดตำแหน่งและรักษาเอกสาร ไม่ย่อหรือแก้เนื้อหาของผู้ใช้

วิดีโอใหม่เก็บใน 3-results/evidence/present และ README มีลิงก์ YouTube จากต้นฉบับ .gitattributes คงการใช้ Git LFS กับ MOV ตามชุดใหม่ ไม่อัปโหลดหรือเปลี่ยน URL แทนผู้ใช้

## Git

ไม่มี git add/commit/push ในงานนี้ รายการเปลี่ยนแปลงของไฟล์ผู้สอนที่มีอยู่ก่อนเริ่มยังคงไว้ และไม่ได้สั่ง restore/reset เพื่อล้างงานของผู้ใช้ ชุดส่งเก่าที่เคย tracked ถูกแทนด้วยชุดใหม่ใน working tree แต่สำเนาเก่าครบใน local_backup ก่อน commit ควรใช้ git status ดูขอบเขตชุดส่งใหม่ตามที่ต้องการ

inventory ก่อนแก้และ Git status ก่อนเริ่มเก็บใน local_backup_20261113; mapping และ diff ของโค้ด/เอกสารอยู่ใน 3-results/organization_qa_20261113
