# ตำแหน่งรูปวงจร วิดีโอ และ CSV ในชุดส่งงาน

เริ่มนับพาธจากโฟลเดอร์ `Week_07_Lab_07_PREPARED_20261105` เมื่อแตก ZIP แล้วจะพบโครงสร้างเดียวกัน

| รายการ | ตำแหน่งในโฟลเดอร์ส่งงาน |
|---|---|
| รูปวงจรฉบับผู้ใช้ | [04_Design/LeLamp_Wiring_User_Final.jpg](<04_Design/LeLamp_Wiring_User_Final.jpg>) |
| วิดีโอเล่นกับคน C1 — 10 นาที 10.95 วินาที | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/คลิปเล่นกับคน_10นาที_C1.MOV](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/คลิปเล่นกับคน_10นาที_C1.MOV>) |
| CSV ภาพรวมรอบเล่น 10 นาที | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv>) |
| CSV ข้อมูลครบ 13 topics | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/ROS13_MESSAGES.csv](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/ROS13_MESSAGES.csv>) |
| CSV จำนวนข้อความแยก 13 topics | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/TOPIC_COUNTS.csv](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/TOPIC_COUNTS.csv>) |
| CSV คำสั่งและ encoder มอเตอร์ ID1–5 | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/JOINT_FEEDBACK.csv](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/JOINT_FEEDBACK.csv>) |
| คำอธิบายข้อมูลและหน่วย | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md>) |
| ผลตรวจความครบและเหตุการณ์รอ ToF | [07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/SESSION_VERIFICATION.json](<07_Evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/SESSION_VERIFICATION.json>) |

รูปวงจรเป็นภาพฉบับล่าสุดที่ผู้ใช้ส่ง `Data Flow-นอกเรื่อง (5).jpg` คัดลอกโดยไม่แก้ไขภาพ แสดงภาค AC/Switching 7.5V/ฟิวส์/Emergency NC, บอร์ดเซอร์โวและมอเตอร์5ตัว, Pi5, ToF, LED, Button, Touch และกล้องผ่านCSI adapter ใช้เป็นรูปการเชื่อมต่อที่ผู้ใช้จัดทำ

วิดีโอชื่อ `คลิปเล่นกับคน_10นาที_C1.MOV` คัดลอกจาก IMG_5749.MOV ความยาวตามmetadata610.947s ส่วนCSVบันทึก600.020s จำนวน7,098snapshots ครบ13topics เป็นรอบC1เล่นกับคนจริง เริ่มด้วยMและกด–ปล่อยปุ่มฐาน5ครั้ง แยกจากชุดcontrolled C0/C1หกรอบเดิม ยังไม่ได้ตรวจframe synchronization จึงไม่ถือว่าเวลา0ของCSVตรงกับframeแรกของคลิป

ข้อมูลดิบ trace.jsonl, metadata.json, summary.json และผลตรวจhashอยู่ในโฟลเดอร์เดียวกับCSV ไม่มีwriterdrop/error มีการรอToFสั้นๆตามSESSION_VERIFICATION.json โดยไม่ลบช่วงดังกล่าว

การเพิ่มภาพและรายการตำแหน่งครั้งนี้ไม่ได้แทรกหรือแก้Wordทั้ง3ไฟล์
