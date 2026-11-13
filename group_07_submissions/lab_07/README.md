# Lab 7 ผลของฮอร์โมนต่อจังหวะ CPG ของ LampBio-Inpire

**กลุ่ม 7 · ทดลองวันที่ 12 พฤศจิกายน 2569**

[ดูวิดีโอเล่นกับโคมจริง 10 นาทีบน YouTube](https://youtu.be/-zckfxbT9Jk?feature=shared) · [เปิดไฟล์วิดีโอต้นฉบับ](1-docs/metadata/local_video.json)

| เอกสารหลัก | เนื้อหา |
|---|---|
| [รายงานผล Word](1-docs/lab_documents/Lab07_Report_Group7.docx) | วิธีทดลอง กราฟที่ใช้แกนเวลาร่วมกัน ผลแยกสามคู่ และข้อจำกัดของการวัด |
| [ใบงาน Word](1-docs/lab_documents/Lab07_Student_Worksheet_TH.docx) · [ใบงาน Markdown](1-docs/markdown/worksheet.md) | คำถามงานวิจัย สถาปัตยกรรม สมการ ตัวชี้วัด ผลบนคอมและหุ่นจริง และคำตอบตามใบงาน |
| [Proposal Word](1-docs/lab_documents/Lab07_Proposal_Group7.docx) · [Proposal PDF](1-docs/lab_documents/Lab07_Proposal_Group7.pdf) | ตัวแปรควบคุม ตารางสิ่งเร้า และแผนการเปรียบเทียบ |

## ผลจากหุ่นจริง

C0 ใช้สิ่งเร้าโดยตรง (R = S) ส่วน C1 ใช้ระดับฮอร์โมน (R = H) เก็บ 3 คู่ รอบละ 180 วินาที ทั้ง 6 รอบผ่านครบ 6 อารมณ์ รวม 21,464 ตัวอย่าง เมื่อปล่อย Touch คาบการส่ายฐาน ID1 ในช่วงที่เหลือของ Happy เฉลี่ย **2.806 วินาทีต่อรอบใน C0 และ 2.750 วินาทีต่อรอบใน C1** โดยให้น้ำหนักแต่ละคู่เท่ากัน ช่วงหลังปล่อยวัดได้ 1–2 รอบต่อการทดลอง ค่าเฉลี่ยการเปลี่ยนคาบของ CPG (M2) ลดลงในสองคู่และเพิ่มขึ้นในหนึ่งคู่

- [กราฟก่อนแตะ ระหว่างแตะ และหลังปล่อย](3-results/figures/01_Happy_input_CPG_and_encoder.png) ขยายช่วงวินาที 39–67 ของรอบทดลอง เริ่ม Touch ที่วินาที 42 และปล่อยที่วินาที 59
- [กราฟคาบ CPG และคาบฐานทั้งสามคู่](3-results/figures/02_Touch_release_all_pairs.png) แต่ละจุดคือคาบเต็มที่วัดได้
- [กราฟทั้งหกอารมณ์ตลอด 180 วินาที](3-results/figures/03_Six_state_timeline.png) แสดงค่า φ ที่ระบบเลือกตามลำดับเวลาจริง
- [ดัชนีหกรอบ](3-results/real_robot/summary/Run_index.csv) · [ตาราง M1 และ M2 ของหุ่นจริง](3-results/real_robot/summary/Worksheet_M1_M2.csv)

## ตรวจตามโจทย์อาจารย์

[ผลตรวจข้อกำหนด Lab 07 ทีละข้อ](1-docs/markdown/lab07_requirements_th.md) รวมตัวตรวจ Proposal และ policy ของอาจารย์ ผล bridge สองเงื่อนไข × สามรอบ และขอบเขตที่โคมใช้สถาปัตยกรรม Raspberry Pi 5

## ตรวจข้อมูลเพิ่มเติม

| ส่วน | หลักฐาน |
|---|---|
| หุ่นจริง | [คำอธิบายข้อมูล](1-docs/markdown/results_guide_th.md) และโฟลเดอร์ P1–P3 ใน [real_robot](3-results/real_robot/) |
| แบบจำลอง | [วิธีรันซ้ำและผลใหม่ 3 คู่](1-docs/markdown/simulation_th.md) ใช้บริบทของ C0 ในคู่นั้นกับทั้งสองเงื่อนไข |
| ระบบและซอร์ส | [แผนภาพทางเดินข้อมูล](4-figures/lamp_data_flow.png) · [ซอร์สและเครื่องมือวิเคราะห์](2-src/) |
| การสาธิต | [คลิปและ CSV](1-docs/markdown/evidence_present_th.md) บันทึกครั้งเดียวตั้งแต่ feedback แรกถึงสุดท้าย 631.926 วินาที รวมช่วง Safety คืนท่า |
| ที่มาของแบบจำลอง | [เอกสารอ้างอิง](1-docs/references/README.md) |

ตรวจ SHA-256 และสัญญาข้อมูลทั้งชุดจากโฟลเดอร์นี้ด้วย `python verify_package.py` บนคอม

## โครงสร้างชุดส่ง

`1-docs` เอกสารและใบงาน, `2-src` โค้ด/config, `3-results` ข้อมูลและหลักฐาน, `4-figures` ผังระบบ ดู [รวมเอกสาร](1-docs/README.md) สำเนาชุดเดิมก่อนจัดเก็บเฉพาะในเครื่องที่ `../../local_backup_20261113/lab07_before/` ชุดเก่าและข้อมูลวันที่ 6–7 พฤศจิกายนไม่ถูกนำมาปนกับผลวันที่ 12 พฤศจิกายน

## วิดีโอสำหรับ GitHub Fork

[ดูคลิปชุดใหม่วันที่ 12 พฤศจิกายน](https://youtu.be/-zckfxbT9Jk?feature=shared) · [ชื่อ/ขนาด/SHA256 ของไฟล์วิดีโอที่เก็บในเครื่อง](1-docs/metadata/local_video.json) ตัววิดีโอไม่อยู่ใน Git tree ส่วน CSV และเอกสารยังรวมครบ [วิดีโอชุดก่อนหน้าและลิงก์ Release เดิม](1-docs/references/previous_video_evidence.md)
