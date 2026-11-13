# สถาปัตยกรรมโคมและการบันทึกข้อมูล

[แผนภาพระบบ](../../4-figures/lamp_data_flow.png) · [Mermaid ที่แก้ไขได้](../../4-figures/lamp_data_flow.mmd) · [ผังสายที่กลุ่มยืนยัน](../../4-figures/lampbio-inpire_wiring_user_final.jpg)

1. ตัวเก็บการทดลองป้อน Button, Touch และ logical Near ตามตารางเดิมทั้งคู่ กล้องจริงให้ตำแหน่งสำหรับการตามหน้า GPIO และ ToF จริงยังส่งข้อมูลให้ตัวควบคุม
2. FSM เลือก Normal, Interested, Happy, Angry, Afraid หรือ Sleepy สาขาควบคุมจังหวะใช้ R = S ใน C0 และ R = H ใน C1 เพื่อกำหนด φ ให้ CPG
3. ตัวถอดจังหวะสร้างเป้ามอเตอร์ ส่งคำสั่งผ่านผู้ควบคุม UART หนึ่งตัวไปยัง STS3215 ห้าข้อ ระบบไฟบน Pi เลือกสีตามอารมณ์และปรับความสว่างของ LED 16 ดวงผ่าน SPI ตามเฟสที่ใช้งาน
4. Encoder และ feedback ทางไฟฟ้าบอกสถานะข้อต่อ ตัวควบคุมความปลอดภัยของ LampBio-Inpire ตรวจแรงต้านที่ ID1, ID2, ID4 และบันทึกเหตุที่ระบบร้องขอให้หยุดกับการคืนท่า
5. Pi บันทึกเหตุการณ์และตัวอย่างภายในเครื่อง แล้วส่งสำเนาให้คอมตรวจ checksum และแปลงเป็น CSV

[สัญญาหัวข้อ ROS 2 จำนวน 13 รายการ](../../2-src/config/topic_contract_13.json) ให้ชื่อ ชนิดข้อมูล หน่วย และ QoS สำหรับการออกแบบตามรายวิชา การบันทึกรอบ 180 วินาทีทั้งหกครั้งใช้ตัวบันทึก native บน Pi JSONL และ CSV มีข้อมูลในช่วงวัด 12 จาก 13 หัวข้อ ข้อมูลกรอบใบหน้าที่บันทึกได้ 4 กรอบอยู่ก่อนเริ่มจับเวลา ส่วน rosbag ของแบบฝึกบนคอมมี 7 หัวข้อ รวม 7,425 ข้อความ


## Bridge สามโหนดสำหรับแบบฝึกบนคอม

[ผังสามโหนดของ Lab 07](../../4-figures/ros_bridge_roles.png) และ [สัญญา 7 หัวข้อของอาจารย์](../../2-src/config/interface_contract.json) ระบุบทบาทของ /week07_inputs, /week07_interaction และ /week07_output_collector ใช้ RELIABLE, KEEP_LAST depth 10 และ VOLATILE สำหรับหัวข้อในแบบฝึก Bool, Float32, String, Float32MultiArray และ ColorRGBA ไม่มี Header ตารางเวลาแบบฝึก offline เก็บ source_id, เวลาแหล่งสัญญาณ, เวลารับและเวลาสั่งในไฟล์ข้างเคียง ส่วนหลักฐาน ROS บนคอมเก็บเวลา callback และเวลารับข้อความตามนาฬิกาของเครื่อง การเทียบกับเวลาที่หุ่นจริงขยับต้องมีแหล่งเวลาและจุดสังเกตทางกายภาพเพิ่ม ดู [ผลแบบฝึก bridge](../../3-results/course_bridge) และ [ผล ROS 2 บนคอม](../../3-results/course_ros)

[เทียบหัวข้อทั้ง 13 กับค่าที่บันทึกได้](../../3-results/coverage/topic_coverage.csv) และ [ยอดหลักฐานแยกตามคู่](../../3-results/real_robot/summary/Topic_coverage_by_run.csv)
