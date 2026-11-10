> **สถานะ GitHub ปัจจุบัน:** วิดีโอจริงเก็บใน [GitHub Releases](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/tag/lab07-video-evidence) แยกจาก Git Tree ดาวน์โหลด [default.mp4 — คลิปทดลองเล่น](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/default.mp4) และ [_10._C1.MOV — คลิปเล่นกับคน 10 นาที](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) ชื่อบน Release ต่างจากต้นฉบับ แต่ digest SHA-256 ตรงกับค่าต้นฉบับที่ระบุ CSV และข้อมูลการทดลองยังอยู่ใน `3-results/evidence` ตามเดิม วิดีโอทั้งสองเป็นหลักฐานการทดลองคนละรอบ ยังไม่ได้ยืนยันการ Synchronize Frame กับ CSV แบบ Frame-by-frame และไม่ถือว่าเฟรมแรกตรงกับเวลา 0 ของ CSV โดยอัตโนมัติ

> ข้อความเรื่องโครงสร้างเมื่อแตก ZIP ด้านล่างเป็นประวัติชุดส่งเดิม สำหรับ GitHub ให้ใช้ลิงก์วิดีโอใน Releases ส่วนพาธ CSV และรูปวงจรยังใช้ได้ตามเดิม

# ตำแหน่งรูปวงจร วิดีโอ และ CSV ในชุดส่งงาน

เริ่มนับพาธจากโฟลเดอร์ `Week_07_Lab_07_PREPARED_20261105` เมื่อแตก ZIP แล้วจะพบโครงสร้างเดียวกัน

| รายการ | ตำแหน่งในโฟลเดอร์ส่งงาน |
|---|---|
| รูปวงจรฉบับผู้ใช้ | [4-figures/lelamp_wiring_user_final.jpg](<../../4-figures/lelamp_wiring_user_final.jpg>) |
| วิดีโอเล่นกับคน C1 — 10 นาที 10.95 วินาที | [_10._C1.MOV — ดาวน์โหลดจาก GitHub Releases](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) |
| CSV ภาพรวมรอบเล่น 10 นาที | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv>) |
| CSV ข้อมูลครบ 13 topics | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/ROS13_MESSAGES.csv](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/ROS13_MESSAGES.csv>) |
| CSV จำนวนข้อความแยก 13 topics | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/TOPIC_COUNTS.csv](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/TOPIC_COUNTS.csv>) |
| CSV คำสั่งและ encoder มอเตอร์ ID1–5 | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/JOINT_FEEDBACK.csv](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/JOINT_FEEDBACK.csv>) |
| คำอธิบายข้อมูลและหน่วย | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md>) |
| ผลตรวจความครบและเหตุการณ์รอ ToF | [3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/SESSION_VERIFICATION.json](<../../3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/SESSION_VERIFICATION.json>) |

รูปวงจรเป็นภาพฉบับล่าสุดที่ผู้ใช้ส่ง `Data Flow-นอกเรื่อง (5).jpg` คัดลอกโดยไม่แก้ไขภาพ แสดงภาค AC/Switching 7.5V/ฟิวส์/Emergency NC, บอร์ดเซอร์โวและมอเตอร์5ตัว, Pi5, ToF, LED, Button, Touch และกล้องผ่านCSI adapter ใช้เป็นรูปการเชื่อมต่อที่ผู้ใช้จัดทำ

วิดีโอชื่อ `คลิปเล่นกับคน_10นาที_C1.MOV` คัดลอกจาก IMG_5749.MOV ความยาวตามmetadata610.947s ส่วนCSVบันทึก600.020s จำนวน7,098snapshots ครบ13topics เป็นรอบC1เล่นกับคนจริง เริ่มด้วยMและกด–ปล่อยปุ่มฐาน5ครั้ง แยกจากชุดcontrolled C0/C1หกรอบเดิม ยังไม่ได้ตรวจframe synchronization จึงไม่ถือว่าเวลา0ของCSVตรงกับframeแรกของคลิป

ข้อมูลดิบ trace.jsonl, metadata.json, summary.json และผลตรวจhashอยู่ในโฟลเดอร์เดียวกับCSV ไม่มีwriterdrop/error มีการรอToFสั้นๆตามSESSION_VERIFICATION.json โดยไม่ลบช่วงดังกล่าว

การเพิ่มภาพและรายการตำแหน่งครั้งนี้ไม่ได้แทรกหรือแก้Wordทั้ง3ไฟล์
