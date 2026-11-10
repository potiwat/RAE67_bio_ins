# เริ่มเก็บที่โคมด้วยปุ่มฐาน5ครั้ง

คำขอผู้ใช้: Mตั้งNormalก่อน แล้วใช้ปุ่มฐาน5ครั้งเป็นเส้นStart ไม่ให้เวลาเดินจากคอมกินช่วงบันทึก Implementเฉพาะprofileใหม่ lab07_button_start_C0_180s.json / C1_180s.json โหมดเล่นปกติและprofileเก่าไม่เปลี่ยน

## วิธีใช้
1. เริ่มวิดีโอ กดM/Startที่คอม รอNormal แล้วเดินไปหน้าโคมได้โดยไม่จับเวลา ขณะนี้รอที่Normal ไม่เข้าSleepy/ApproachหรือเดินCPG/AHM
2. กด–ปล่อยปุ่มฐานให้ครบ5ครั้ง ไม่กำหนดช่วงเวลารัว ค้างไม่นับซ้ำ กดก่อนNormalพร้อม/ก่อนเห็นปุ่มปล่อยครั้งแรกไม่นับเป็นรอบสมบูรณ์
3. ปล่อยครั้งที่5และปล่อยTouchด้วย เป็นจุดเริ่มบันทึก หน้าจอเปลี่ยนเป็นRecording ห้าครั้งเตรียมไม่ทำให้Interestedและไม่ถูกreplayเป็นS/H หลังเริ่ม ปุ่มครั้งถัดไปใช้Interestedตามปกติ
4. นับจากปล่อยครั้งที่5: +3sปุ่มฐาน1ครั้ง; +12sTouch1ครั้ง; +15sTouch3ครั้งใน2s; +24–26sมือNearแล้วเอาออก; ปล่อยจนSleepyแล้วรองรับQจบได้ตามที่ผู้ใช้อนุมัติ

เพดานยัง180sนับจากเริ่มจริง Qก่อนเพดานยังรายงานpartial/incompleteตามเกณฑ์เดิม เป็นpilot ไม่ใช่final600s3คู่ ไม่แก้summaryเพื่อทำPASS

## การตรวจจุดเริ่ม
ก่อนStart gateไม่เรียกdecoder/FSMธรรมดา จึงไม่ต้องรีเซ็ตoscillatorที่กำลังเคลื่อนเมื่อเริ่ม ใช้bankที่ยังไม่advanceและAHM H=0 พร้อมfade2sเดิม แถวแรกมีmeasurement_startเก็บowner started_s, source_release_s, counterbaselineและinitial_oscillator_bank ทั้ง3ตัว ให้เทียบข้อมูลจริงC0/C1ก่อนอ้างว่าเริ่มตรงกัน

rawdigitalcounterเป็นยอดตั้งแต่เปิดsampler รวม5ครั้งเตรียม ต้องลบdigital_counter_baselineเพื่อหาจำนวนinputทดสอบ ไม่ซ่อนหรือแก้counter/rawedges ห้าครั้งไม่ปรากฏเป็นFSMinteraction

## Safety/การฟื้น
ยังตรวจcontrollerfeedback/กล้องค้าง/STOPและToFเดิม ช่วงNearไม่อนุญาตเริ่มและรีเซ็ตตัวนับ เมื่อToFสะดุดก่อนเริ่มแล้วฟื้นจะกลับNormalผ่านrouteเดิมที่ตรวจboundsก่อน ไม่ติดdistance_wait หากNearกลับมาระหว่างrouteคืนNormalให้hold/cancelและรอClearก่อนเดินrouteใหม่ ไม่ปล่อยtorqueหรือเพิ่มขอบมุม

## หลักฐานซอฟต์แวร์
- unitgate5tests และowner-loop5testsผ่าน: held/bounce/startup press, fifth release, next button, stop, ToF recovery/near interruption
- ทดสอบC0/C1รอเตรียม8และ20วินาที: firstsample H=0,S=0,o1/o2/decoderphaseตรงกัน และbankยังupdates0ก่อนเริ่ม ไม่ถือเป็นการพิสูจน์เครื่องจริง
- runtime520testsผ่าน; shared245testsข้าม1ที่เหลือผ่าน; ownerloop+play sweep11methodsผ่าน; Pi mocked69testsผ่าน
- code reviewพบToF-recoverydeadlockและNearguardระหว่างrestoreก่อนdeploy เพิ่มreproductiontestsและแก้แล้ว
- backup/hashes/deploymentreport: ../play_clean_audit_20261105/button_gate_deployment.json

เปิดviewerใหม่รอผู้ใช้M/Start ไม่สั่งมอเตอร์จากการdeployหรือtests ผลฮาร์ดแวร์ของgateใหม่นี้ยังรอรอบผู้ใช้ยืนยัน

## สัญญาณไฟเริ่มรอบที่ผู้ใช้ขอเพิ่ม
ขณะกดMตั้งNormalและรอปุ่ม5ครั้ง ไฟดับ เมื่อปล่อยครบ5จึงเปิดไฟNormalขาว3%พร้อมเริ่มรอบ ไม่มีการเพิ่มไฟกระพริบหรือสีใหม่ ใช้drivercloseเดิมให้DINกลับLOWระหว่างดับ ตัวทดสอบLEDgate/behavior/driverและownerloop32ข้อผ่านบนคอม และชุดที่เกี่ยวข้อง27ข้อบนPiผ่าน รายละเอียดbackup/hashใน ../play_clean_audit_20261105/button_start_led_deployment.json การเห็นไฟในวิดีโอเป็นmarkerเชิงสังเกต ไม่รับรองlatencyแสงเท่ากับsoftwaretimestampโดยไม่มีการวัด
