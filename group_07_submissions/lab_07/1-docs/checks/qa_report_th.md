> อัปเดต: ผู้ใช้ส่ง read_only_bus.py เพิ่มแล้ว จัดที่ `2-src/calibration_readonly/read_only_bus.py` สำเนาเดิมอยู่ `original_files/added_dependencies` ตรวจ checksum/syntax และ mock transport/baseline ผ่าน 25 tests ข้อความขาด dependency ด้านล่างเป็นผลตรวจรอบก่อนรับไฟล์ ไม่ใช่สถานะปัจจุบัน ยังไม่ได้รัน ROS2/Pi/hardware จริง

# รายงาน QA และแก้การจำแนก Lab07 — 6 พฤศจิกายน 2026

**ผลรวม: ยังไม่ครบ Definition of Done** — ไม่พบไฟล์สูญหาย และแก้รายการจำแนก/path ที่พิสูจน์ได้แล้ว แต่ source ยังขาด read_only_bus.py (calibration_readonly) ที่บางโมดูลต้อง import จึงไม่รับรอง runtime หรือความพร้อมส่งทั้งหมด

## A. Repository conventions found

อ่าน repository จริง C:/Users/USER/Desktop/BioInspired-Robotics-Labs ครบ Lab02–Lab06, root README และ .gitignore: Lab02–Lab05 ใช้ 1-docs, 2-src, 3-results, 4-figures; Lab06 ไม่มี 4-figures รายงาน Word ของ Lab04–05 ใช้ LabXX_Report_Group7.docx และรายงาน Lab06 ใช้ Lab06_Report_Group7.pdf อยู่ใน 1-docs ส่วน worksheet.md อยู่ 1-docs โค้ดส่วนใหญ่ lowercase; raw IDs/snapshots อาจมี uppercase

Lab07 รักษา 4 หมวดหลักและโฟลเดอร์ย่อยเอกสารที่ผู้ใช้สั่งแยกไว้ Word ใช้ชื่อ Lab07_* ตาม convention เดิม ไม่เรียก worksheet ว่า manual ไม่แก้ Lab เก่า ข้อมูล baseline ทุกไฟล์และ Git status อยู่ repository_baseline.json

## B. File classification report

ตารางครบทุกไฟล์ ณ เริ่ม audit 1,777 ไฟล์ รวม 875 active และ 902 backup อยู่ [classification_inventory.csv](../../3-results/repository_qa_20261106/classification_inventory.csv) และ [JSON](../../3-results/repository_qa_20261106/classification_inventory.json)

แต่ละแถวมีชื่อ/path เดิม, extension, detected type, size, SHA256, สรุปเนื้อหา, หน้าที่, related files, final location, status และหลักฐานการจำแนก ไม่ใช้ extension เพียงอย่างเดียว: parse Python AST/JSON/JSONL/CSV/XML, อ่าน word/document.xml, อ่าน signature ภาพ/วิดีโอ/SQLite/MCAP และดึงข้อความ PDF ด้วย pypdf ตรวจ YAML แยกด้วย PyYAML ไม่มีการ execute source เพื่อเดาหน้าที่

PDF proposal มี 3 หน้าและเนื้อหาข้อเสนอโครงงาน ส่วน PDF อีกฉบับเป็นกราฟ S/H/phi 1 หน้า จึงย้ายกลับ experiment bundle ของ pilot ไม่จัดเป็น lab report การอ่าน PDF นี้ไม่ใช่การตรวจ layout หรือคุณภาพภาพด้วยสายตา

Human-written guides/protocols/technical reports ย้ายเข้า 1-docs/markdown; generated metrics/log/QA outputs อยู่ 3-results; ภาพและ diagram source อยู่ 4-figures; topic contract อยู่ 2-src/Lab07/config โค้ด package-local README มีเหตุผลด้านการใช้งานจึงคงไว้กับ package; course worksheet เก่าใน worksheet_review เป็น pinned provenance/static input bundle ไม่ใช่ worksheet Lab07 ที่จัดผิด

แยก recorded measurements/analysis ออกจาก shared/hardware ไป 3-results/hardware_characterization โดยเก็บ runtime pose/PID/config ที่โค้ดใช้จริงไว้ ไม่แตะ source_snapshot หรือข้อมูลการทดลองเพื่อให้ผลเปลี่ยน

## C. Filename validation report

ย้าย/เปลี่ยนชื่อ 51 รายการ ดู [dry-run mapping](../../3-results/repository_qa_20261106/dry_run_mapping.json) และ changes.json พร้อมเหตุผลทุกไฟล์ ตรวจปลายทางและ case-insensitive collisions ก่อนทำ ไม่มี collisions และไม่เขียนทับ

เปลี่ยนชื่อ manifest เป็น manifest_sha256.json ให้ตรงกับ verifier บน Linux ชื่อเอกสารใหม่ใช้ lowercase ยกเว้น README.md และ Word/PDF Lab07_* ตาม convention ที่ตรวจพบ ชื่อ P1/C0/C1 และ raw/snapshot/provenance เดิมคงไว้เพราะมี reference/hash; รายการข้อยกเว้นครบใน naming_audit.json ไม่มีการลบ byte-identical duplicates

แก้ relative Markdown links และ live dataset references เพิ่ม ament resource marker ที่ setup.py อ้างถึงแต่ขาดอยู่ แก้ verify_evidence.py ให้ใช้ชุดข้อมูล course_bridge จริงและ print ผลตรวจโดยไม่เขียนทับ verification.json ของการทดลองเดิม แก้ export_review_csv.py ให้ resolve input/output จาก root Lab07 ไม่ใช่โฟลเดอร์ source; ไม่สั่ง export สร้างข้อมูลทดลองใหม่

รายการ modified files และ diff อิสระจากสำเนาก่อนแก้: modified_files.json และ independent_diffs.diff ไฟล์ก่อนแก้ทุกไฟล์เก็บใน _originals_20261106/qa_repair_before

## D. Final directory tree

ดู [tree ชุดใช้งานครบ](../../3-results/repository_qa_20261106/directory_tree.txt) และ [tree รวม backup ครบ](../../3-results/repository_qa_20261106/directory_tree_with_backups.txt) แสดงชื่อจริงทุกไฟล์ ไม่มี placeholder

## E. Quality assurance report

| รายการ | ผล | หลักฐาน/ขอบเขต |
|---|---|---|
| File integrity | PASS | original bytes เดิม 866 รายการและไฟล์ ณ เริ่มตรวจทุกไฟล์ยังพบ SHA256 ครบ; final_reconciliation.json |
| Missing-file audit | PASS | ไม่มี missing original bytes, missing audit-start bytes หรือ missing mapped files |
| Classification accuracy | PASS เฉพาะ functional audit | ตรวจเนื้อหาและย้ายข้อผิดประเภทที่ชัดเจน; pinned snapshots/package-local docs/bundle companion มีเหตุผลระบุ ไม่รับรอง scientific validity ของผลทดลอง |
| Filename consistency | PASS พร้อมข้อยกเว้น | naming_audit.json; raw/provenance names และ convention Word คงไว้ |
| Duplicate/collision audit | PASS | ไม่มี case collisions; byte-identical active duplicates 119 กลุ่ม/202 สำเนาเกิน ณ รอบ reconciliation เก็บครบ ไม่ deduplicate |
| Dependency integrity | FAIL | read_only_bus.py ไม่อยู่ในชุดที่รับมา โค้ด motor_baseline.py, normal_gaze_motor.py, yaw_gain_trial.py และ test_manual_transport.py อ้างถึง calibration_readonly |
| Documentation links | PASS | ตรวจ local Markdown/image links ทุก active Markdown หลังย้าย มีรายงาน markdown_links.json; ข้อความ path ใน prose/code examples และเอกสาร upstream เป็นประวัติ ไม่ใช่ผลรันรับรองบนเครื่องนี้ |
| Code syntax | PASS | Python active ทั้งชุด parse AST ผ่าน; จำนวนใน independent_qa.json รวม snapshots |
| Mock tests | PASS | 119 tests; mock.log |
| Policy | PASS | 40 transition pairs, failures=0; policy.log |
| Proposal | PASS เฉพาะ field completeness | proposal.log; ไม่ใช่รับรองวิทยาศาสตร์หรือคะแนน |
| Recorded evidence check | PASS | recorded_evidence.log; manifests, model bounds, derived CSV และ byte-identical replay; ไม่แก้ raw |
| ZIP safety/integrity | PASS | 12 ZIP รวม backup; อ่านทุกสมาชิกตรวจ CRC/hash, traversal, symlink, duplicate names ไม่พบปัญหา ไม่แตกไฟล์ ไม่มี nested ZIP member |
| ROS2 package static | PASS | package.xml parse, setup.py และ resource marker มีจริง; ไม่มี launch file ใน active package |
| ROS2/Pi imports, colcon build, hardware | NOT TESTED | ไม่มี ROS/Pi libraries ใน Windows; ไม่เปิด GPIO/UART/กล้องหรือสั่งมอเตอร์ |
| PDF/video visual/frame alignment | NOT TESTED | ตรวจ PDF text และ binary/container integrity เท่านั้น |

missing external imports ทั้งชุดอยู่ independent_qa.json รวม rclpy/std_msgs/ROSbag, Pi camera/GPIO/I2C/LED libraries, setuptools และ read_only_bus; ไม่ติดตั้ง hardware libraries หรือเรียกอุปกรณ์เพื่อฝืนให้ผ่าน PDF/YAML parser ใช้ isolated temporary library ไม่แก้ runtime ของโครงงาน

## F. Final reconciliation

- Original historical baseline: 866 files, SHA256 เดิมยังพบครบใน current/backup
- Audit-start files: 1,777 = active 875 + historical backups 902
- Missing mapped destination: 0; missing original bytes: 0; missing audit-start bytes: 0
- ย้าย/เปลี่ยนชื่อ 51 รายการ; 3 รายการเป็น .pyc ย้ายเก็บ backup เท่านั้น ไม่ลบทิ้ง
- Modified original files: 9 รายการ ณ reconciliation (ดู modified_files.json); README สรุปผล audit เพิ่มหลังรอบดังกล่าวและเก็บฉบับก่อนแก้แล้ว
- เพิ่ม ament resource marker 1 ไฟล์และรายงาน/ตาราง/ผลตรวจ QA เท่านั้น ไม่มี PDF/ข้อมูลทดลองใหม่
- จำนวน active/backup สุดท้ายและไฟล์เพิ่มใหม่เทียบเริ่มงานอยู่ final_counts.json เพราะรวม QA artifacts เพิ่มจาก baseline
- ZIP คงเป็น archive เดิม ไม่แตกเป็น active dataset จึงไม่นำ member count มาบวก original files
- ไม่มีไฟล์ถูกทิ้งเป็น unclassified staging; unresolved คือ dependency และการทดสอบ environment ตามข้างต้น ไม่ใช่ไฟล์สูญหาย

## G. Git review

Reference repository มี untracked extra/ อยู่ก่อนงาน และไม่ถูกแก้ Lab07 เป้าหมายไม่ใช่ Git checkout จึงไม่มี git diff/status ของ target ให้รายงานเป็น successful Git review ใช้ SHA256 และ diff จาก pre-change backup แทน ไม่มี commit/push และไม่มี destructive Git commands

วิดีโอ 10 นาทีขนาด 616,429,505 bytes ยังเก็บอยู่ครบ หากเผยแพร่ต้องเลือก LFS/hosting; ไม่อัปไฟล์ให้ผู้ใช้โดยพลการ .gitignore กัน _originals, caches และทั้ง .mov/.MOV ไว้แล้ว

**สิ่งที่เหลือ:** นำ source dependency read_only_bus.py/calibration_readonly เวอร์ชันที่ตรงกับหุ่นจริงมาตรวจและรวมอย่างมีที่มา แล้ว build/test ROS2 บน environment ที่เหมาะสม จึงจะสรุปว่าชุด source พร้อมใช้งานครบได้ รอบนี้ไม่สร้าง bus implementation ทดแทนหรือแต่งผลทดสอบ
