# หลักฐานวิดีโอ Lab07 — กลุ่ม 7

## สถานะบน GitHub

ไฟล์วิดีโอจริงอยู่ใน [GitHub Release: Lab07 - Group 07 Video Evidence](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/tag/lab07-video-evidence) (Tag: `lab07-video-evidence`) ไม่ได้อยู่ใน Git Tree ของ `3-results/evidence` ส่วน CSV, JSON และข้อมูลการทดลองยังอยู่ในโฟลเดอร์หลักฐานนี้ตามเดิม

| ชื่อคลิปต้นฉบับ | ระยะเวลา | วัตถุประสงค์ | ดาวน์โหลดวิดีโอ | ข้อมูล CSV ที่เกี่ยวข้อง |
|---|---|---|---|---|
| คลิปทดลองเล่น.mp4 | 167.05 วินาที (2:47.05) | หลักฐานประกอบรอบเล่นกับโคม C1 และข้อมูล diagnostic ที่กู้คืน | [default.mp4](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/default.mp4) | [CSV รอบทดลองเล่น](<CSV ของ วิดีโอทดลองเล่น/CSV ของ วิดีโอทดลองเล่น.csv>) |
| คลิปเล่นกับคน_10นาที_C1.MOV | 610.947 วินาที (10:10.947) | หลักฐานรอบเล่นกับคน C1 เพิ่มเติม แยกจากชุด controlled C0/C1 | [_10._C1.MOV](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) | [CSV รอบเล่นกับคน 10 นาที](<CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv>) |

## ชื่อไฟล์ ขนาด และ SHA-256

| ชื่อไฟล์ต้นฉบับ | ชื่อบน Release | ขนาด (bytes) | SHA-256 |
|---|---|---:|---|
| คลิปทดลองเล่น.mp4 | default.mp4 | 39,881,620 | `c073c06bc7729733ee3b3f7e5865bbf451a057d65eda2beb3f08d110b8bc67fd` |
| คลิปเล่นกับคน_10นาที_C1.MOV | _10._C1.MOV | 616,429,505 | `8e1796da36ef4d04ce3d4bd068975b2a616cec8666674f47958584d3fd60380a` |

ตรวจผ่าน GitHub Release API แล้วว่า Asset ทั้งสองมีสถานะ `uploaded` ชื่อ ขนาด digest SHA-256 และ URL ดาวน์โหลดตรงกับข้อมูลต้นฉบับที่ระบุ แม้ชื่อไฟล์บน Release จะแตกต่างจากชื่อเดิม ระยะเวลาวิดีโออ้างอิง metadata ที่บันทึกไว้เดิม ไม่ใช่ผลการตรวจเนื้อหาภาพในการอัปเดตเอกสารครั้งนี้

## ข้อมูลรอบทดลองเล่น 167.05 วินาที

[CSV diagnostic](<CSV ของ วิดีโอทดลองเล่น/CSV ของ วิดีโอทดลองเล่น.csv>) ยาว 180.98 วินาที ผู้ใช้ยืนยันลำดับ Sleepy→Afraid→Happy สอดคล้องกัน แต่ยังไม่ได้ตรวจจุดเริ่มตรงเฟรม ไม่อ้างว่าไฟล์มีความยาวเท่ากันหรือเป็น human scenario 600 วินาที ชุดอัตโนมัติ 600 วินาที/6 รอบแยกใน [real_robot_final](../real_robot_final/)

## รอบเล่นกับคน 10 นาทีเพิ่มเติม วันที่ 6 พฤศจิกายน 2026

[CSV และข้อมูลดิบรอบ C1](CSV_คลิปเล่นกับคน_10นาที_C1_20261106/README_TH.md) เก็บจริง 600.02 วินาที / 7,098 snapshots / 13 topics / 85,032 message rows เริ่มจากปุ่มฐาน 5 ครั้ง เก็บครบและไม่มี writer drop มี WAIT_TOF สั้น 3 ช่วงตามรายงาน ดาวน์โหลดวิดีโอรอบนี้จาก [_10._C1.MOV](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) ความยาว 610.947 วินาที คลิป 167.05 วินาทีด้านบนเป็นคนละรอบ

วิดีโอทั้งสองเป็นหลักฐานการทดลองคนละรอบ ยังไม่ได้ยืนยันการ Synchronize Frame กับ CSV แบบ Frame-by-frame และไม่ถือว่าเฟรมแรกตรงกับเวลา 0 ของ CSV โดยอัตโนมัติ วิดีโอทั้งสองไม่ใช้แทนหรือรวมเป็น paired trials ของชุด controlled C0/C1 โดยอัตโนมัติ
