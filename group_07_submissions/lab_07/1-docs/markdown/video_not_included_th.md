> **สถานะ GitHub ปัจจุบัน:** วิดีโอจริงเก็บใน [GitHub Releases](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/tag/lab07-video-evidence) แยกจาก Git Tree ดาวน์โหลด [default.mp4 — คลิปทดลองเล่น](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/default.mp4) และ [_10._C1.MOV — คลิปเล่นกับคน 10 นาที](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) ชื่อบน Release ต่างจากต้นฉบับ แต่ digest SHA-256 ตรงกับค่าต้นฉบับที่ระบุ CSV และข้อมูลการทดลองยังอยู่ใน `3-results/evidence` ตามเดิม วิดีโอทั้งสองเป็นหลักฐานการทดลองคนละรอบ ยังไม่ได้ยืนยันการ Synchronize Frame กับ CSV แบบ Frame-by-frame และไม่ถือว่าเฟรมแรกตรงกับเวลา 0 ของ CSV โดยอัตโนมัติ

> **หมายเหตุประวัติ:** ข้อความด้านล่างอธิบายขั้นตอนและสถานะของชุด local/ZIP ในอดีต ไม่ใช่สถานะการเผยแพร่บน GitHub ปัจจุบัน และไม่จำเป็นต้องนำวิดีโอเข้า Git Tree หรือ Git LFS เพื่อเปิดหลักฐานบน GitHub

# ZIP สำหรับส่งต่อ — เว้นวิดีโอ10นาที

ผู้ใช้ขอไม่รวมวิดีโอ10นาทีในZIPนี้ เพื่อลดขนาดไฟล์และให้ผู้รับใส่ภายหลัง CSV/รูปวงจร/Word/ผลทดลองอื่นยังอยู่ครบ

นำไฟล์ `คลิปเล่นกับคน_10นาที_C1.MOV` ไปใส่ที่:

`3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/คลิปเล่นกับคน_10นาที_C1.MOV`

ไฟล์วิดีโอที่ถูกต้องยาว610.947วินาที ขนาด616,429,505bytes SHA256: 8e1796da36ef4d04ce3d4bd068975b2a616cec8666674f47958584d3fd60380a

ต้นฉบับวิดีโอในโฟลเดอร์ส่งงานบนเครื่องผู้ใช้ยังอยู่ ไม่ได้ถูกลบ คลิปทดลองเล่นเดิม167.05sเป็นคนละรอบและยังแนบในZIP ไม่ใช่คลิป10นาที

manifestในZIPนี้ตรวจไฟล์ที่แนบจริงก่อนเพิ่มวิดีโอ หากเติมคลิปและต้องการmanifestฉบับครบ ให้สร้างmanifestใหม่ด้วย
