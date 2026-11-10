# Interested เงยผิดหลังออกจาก Happy

เก็บบันทึกเครื่องจริง physical_before.json ก่อนแก้ โดยผู้ใช้Qปิดแล้ว ไม่สั่งมอเตอร์จากการวิเคราะห์/ทดสอบ

## หลักฐานและสาเหตุ
ช่วง4752.19sเข้าbutton lookจากท่ายืดสูง มีเป้าID2/3=2605/3046, ID4=1693, ID5=2164 (actual2607/3082/1877/2183) โค้ดfallbackเก็บเป้าทั้งห้า แต่ทับเฉพาะID2/3ด้วยrhythm_base_referenceเก่าที่เป็นNormal2837/2746 โดยไม่ชดเชยหัวหรือคืนคอ จึงได้ท่าประกอบคนละreference

button_return_traceจบ4759.51sด้วยเป้าID2/3=2837/2746 แต่ID4=1693และID5=2164 ทำให้แขนปกติแต่หัวเงยตามท่าสูงHappyจริง ไม่ใช่ผู้เล่นออกจากกล้องเองหรือการตั้งSpeedC0/C1ต่างกัน

## แก้
fallbackของชุดinterested_gentle_entryปัจจุบันใช้awake_player_reference: ย้ายbody/rollไปNormalแล้วแปลงpitchด้วยเครื่องหมายเดียวกับInterestedHead (`q5 + (normal2-q2) - (normal3-q3)`) จำกัดด้วยกรอบpitchปกติเดิมและคงyaw มุม2164ในตัวอย่างจึงกลับ2696พร้อมbodyNormal ไม่เอาหัวHappyไปจับคู่bodyNormalตรงๆ

ใช้helperเดียวกันขณะเก็บreferenceก่อนSleepyในทางnonbusy ป้องกันHappy→Sleepy→ปุ่มฐาน ส่วนexplicit saved referenceที่เป็นท่าประสานกันอยู่แล้วและเส้นทางbusyยังเก็บทั้งชุด ไม่เอาCPGcenterมาทับอีก Legacyprofileที่ไม่มีflagไม่เปลี่ยนพฤติกรรม

ไม่แก้PID ความเร็ว ความเร่ง มุมเต้น ขอบตามหน้า สูตรAHM/CPG หรือค่าEEPROM การแปลงนี้เป็นแบบจำลองorientationเชิงประจักษ์เดิม ไม่ใช่FK/IKหรือการรับรองเล็งหน้าตรงเป๊ะเมื่อtranslation/roll/โหลดจริงต่างกัน

## ตรวจ
- บั๊กจำลอง3กรณีล้มก่อนแก้ (Happy, repeatedInterested, NormalCPGheadbias) และผ่านหลังแก้
- เพิ่มSleepy-save regression และowner-loopHappy→ปุ่มฐานขณะไม่มีหน้าตลอดรอบ ยืนยันbody/rollreturnNormalและheadเป้าอยู่ในกรอบตื่น
- runtime525testsผ่าน; owner-loop/play/input-start sweeps12methodsผ่าน; reviewแยก57relatedtestsผ่าน
- ลงPiพร้อมbackup/hashและrelated76testsผ่าน ดู ../play_clean_audit_20261105/interested_reference_deployment.json
- เปิดC1โหมดเล่นปกติรอStartกลับให้ ไม่กดเริ่มมอเตอร์เอง ต้องให้ผู้ใช้ดูผลจริงหนึ่งรอบก่อนอ้างว่าท่ากลับมองหน้าถูกแล้ว

ผลทดลอง/วิดีโอเก่ายังคงrawเดิม ไม่แก้ให้เป็นผลของรุ่นแก้นี้
