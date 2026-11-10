# งานส่งรายวิชา Bio-Inspired Robotics — กลุ่ม 7

## วิดีโอหลักฐานการทดลอง Lab07

วิดีโอทั้งสองไฟล์เผยแพร่ผ่าน [GitHub Releases](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/tag/lab07-video-evidence) เนื่องจากไฟล์วิดีโอขนาดใหญ่ต้องจัดเก็บแยกจาก Source Code และข้อมูลการทดลองใน Repository ขอความกรุณาผู้สอนดาวน์โหลดจากลิงก์ Release โดยตรง ข้อมูล CSV, JSON, ROS bag และรายงานการทดลองยังอยู่ในโฟลเดอร์ Lab07 ตามเดิม

| ชื่อคลิปต้นฉบับ | ระยะเวลา | วัตถุประสงค์ | ดาวน์โหลดวิดีโอ | ข้อมูล CSV ที่เกี่ยวข้อง |
|---|---|---|---|---|
| คลิปทดลองเล่น.mp4 | 167.05 วินาที (2:47.05) | หลักฐานประกอบรอบเล่นกับโคม C1 และข้อมูล diagnostic ที่กู้คืน | [default.mp4](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/default.mp4) | [CSV รอบทดลองเล่น](<lab_07/3-results/evidence/CSV ของ วิดีโอทดลองเล่น/CSV ของ วิดีโอทดลองเล่น.csv>) |
| คลิปเล่นกับคน_10นาที_C1.MOV | 610.947 วินาที (10:10.947) | หลักฐานรอบเล่นกับคน C1 เพิ่มเติม แยกจากชุด controlled C0/C1 | [_10._C1.MOV](https://github.com/Tonkao1725/BioInspired-Robotics-Labs-Fork-/releases/download/lab07-video-evidence/_10._C1.MOV) | [CSV รอบเล่นกับคน 10 นาที](<lab_07/3-results/evidence/CSV_คลิปเล่นกับคน_10นาที_C1_20261106/CSV_คลิปเล่นกับคน_10นาที.csv>) |

วิดีโอทั้งสองเป็นหลักฐานการทดลองคนละรอบ ยังไม่ได้ยืนยันการ Synchronize Frame กับ CSV แบบ Frame-by-frame และไม่ถือว่าเฟรมแรกตรงกับเวลา 0 ของ CSV โดยอัตโนมัติ รายละเอียดชื่อไฟล์บน Release ที่แตกต่างจากต้นฉบับ พร้อมขนาดและ SHA-256 ที่ตรงกัน อยู่ใน [VIDEO_INDEX.md](lab_07/3-results/evidence/VIDEO_INDEX.md)

นักศึกษาได้ทำ Lab02–Lab07 และบันทึกงานผ่าน GitHub Repository ส่วนตัวตามลำดับสัปดาห์ ก่อนทราบข้อกำหนดว่าต้อง Fork Repository ของผู้สอนโดยตรง จึงได้ย้ายสำเนางานทั้งหมดมายัง Fork นี้ เพื่อให้ผู้สอนสามารถเข้าตรวจสอบงานได้สะดวกและเป็นไปตามข้อกำหนด

**พื้นที่ตรวจงานของกลุ่ม 7: [group_07_submissions](./)**

| งาน | โฟลเดอร์ส่งงาน |
|---|---|
| Lab02 | [lab_02](lab_02/) |
| Lab03 | [lab_03](lab_03/) |
| Lab04 | [lab_04](lab_04/) |
| Lab05 | [lab_05](lab_05/) |
| Lab06 | [lab_06](lab_06/) |
| Lab07 | [lab_07](lab_07/) |
| งานเพิ่มเติม | [extra](extra/) |

โฟลเดอร์ lab_02–lab_07 ที่ Root เป็นไฟล์ต้นฉบับของผู้สอน ส่วนงานของนักศึกษาอยู่ใน group_07_submissions ตามลิงก์ข้างต้น โดยคงไฟล์ original_files ที่ Git ติดตามใน Lab07 ไว้ครบถ้วน

## ประวัติการบันทึกงาน

**ขอความกรุณาผู้สอนตรวจสอบประวัติการทำงานรายสัปดาห์เพิ่มเติมจาก Repository เดิม**

Repository เดิม: [https://github.com/Tonkao1725/BioInspired-Robotics-Labs](https://github.com/Tonkao1725/BioInspired-Robotics-Labs)

| งาน | วันที่ Commit เดิม (ICT) | Commit |
|---|---|---|
| Lab02 | 24 ก.ย. 2569 18:00 | [e2a1910](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/e2a1910b43277875c1d4725a25572ebe99b832b1) |
| Lab03 | 26 ก.ย. 2569 19:59 | [05171e2](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/05171e28c6b60099cb87aa025dbc072531369301) |
| Lab04 | 11 ต.ค. 2569 21:42 | [34260bb](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/34260bb6798b4b54e421634126bb17b8389dbd61) |
| Lab05 | 16 ต.ค. 2569 22:25 | [a96e964](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/a96e964bab4d1e2474605c22948696b36f28e4ed) |
| Lab06 | 21 ต.ค. 2569 22:44 | [3ff381e](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/3ff381ee1091fad332b4c496d7c13d3cc67e5c4c) |
| Lab07 | 6 พ.ย. 2569 15:17 | [0202658](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/020265895344b919282aad32c6dad4ad426fb091) |

วันที่แสดงเป็นเวลา ICT (UTC+7) Commit เหล่านี้เป็นหลักฐานลำดับการบันทึกงาน ไม่ใช่หลักฐานยืนยันเวลา Push หรือการส่งถึงผู้สอนโดยตรง การพิจารณาว่าเป็นการส่งทันกำหนดหรือไม่เป็นดุลยพินิจของผู้สอน

มีการปรับปรุงรายงานและ Worksheet ของ Lab07 เมื่อวันที่ 7 พฤศจิกายน 2569 เวลา 21:26 ICT ใน Commit [bf905df](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/bf905df35eb5cc48756455a8d3a91afb749f3914) และนำไฟล์ proposal PDF ออกเมื่อเวลา 21:27 ICT ใน Commit [c3fb4dc](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/c3fb4dc28c208175c3bec738fac60666435ea02c) ตามประวัติเดิม โดยไม่ได้เปลี่ยนวันที่หรือเขียนประวัติ Commit ใหม่

จุดอ้างอิงการย้ายสำเนา: Commit ล่าสุดของ origin/main ใน Repository เดิม [c588337](https://github.com/Tonkao1725/BioInspired-Robotics-Labs/commit/c58833790d614a569a0078b1b98291db3ce357b5) ซึ่งมีไฟล์ Lab02–Lab07 และ extra เหมือนกับ Commit c3fb4dc ที่มีอยู่ในเครื่องทุกไฟล์ ความต่างมีเฉพาะ README.md ที่ Root ของ Repository เดิม ซึ่งไม่ได้นำมาคัดลอก
