# แนวทางอาจารย์ที่นำมาต่องานโคม

ตรวจ 29 ตุลาคม 2026 จาก repository https://github.com/potiwat/RAE67_bio_ins ที่ commit fa528b169f1127ee3e0e9fae3d721546bf1b82d2 (ชื่อเจ้าของ repository คือ potiwat)

ผู้ใช้ต้องการตรวจวิธีอาจารย์ก่อนเลือกวิธีภายนอก เอกสารนี้เป็นการเทียบแนวทาง ยังไม่ได้ติดตั้งแพ็กเกจ เปลี่ยนค่าหรือสั่งมอเตอร์

| Lab | จุดอ้างอิงในโค้ดอาจารย์ | ใช้กับงานเราอย่างไร |
|---|---|---|
| 02 | lab_02/lab02.py: Controller._filter, Controller.step, calculate_metrics | กรองระยะ ToF ด้วย low-pass; ใช้เกณฑ์เข้า/ออกต่างกัน (hysteresis) ลดการสลับสถานะใกล้ขอบ; จำกัดคำสั่งและตรวจข้อมูลเสีย มี mean_abs_command_change สำหรับเปรียบเทียบคำสั่ง |
| 03 | lab_03/student_cpg.py และ README | SO(2) CPG สร้างจังหวะต่อเนื่อง ใช้สร้างการโยก/เอียงตามอารมณ์ ต้องแปลงเป็นมุมของโคม ไม่ใช้ decoder ขาแมลงโดยตรง |
| 04 | lab_04/student_hormone.py | การผลิต/ลดฮอร์โมน, receptor และ clamp เป็นฐาน AHM ของกลุ่ม; ใช้สถานะเก่าในการคำนวณอัตราก่อนอัปเดต |
| 05 | lab_05/course_model.py: hormone_step, mapped_parameters, step_cpg | เชื่อม AHM–CPG และจำกัดพารามิเตอร์ รองรับ phi-only ตรงกับแผนที่กลุ่มปรับเฉพาะ φ; สอง output CPG คำนวณจากคู่ค่าเก่าเดียวกัน |
| 06 | lab_06/course_model.py: SensorFilter, target_pose, bounded_step | แยกการอ่าน/แปล input ออกจากท่าอารมณ์; debounce/stale/hysteresis; จำกัดมุมและขนาดการเปลี่ยนมุมต่อรอบ ไม่กระโดดไปท่าเป้าทันที |
| 07 | lab_07/lamp_week07/bridge.py: Engine.step, event_rows, normalized_rgb, servo_message | รักษา 5 state, priority, timeout/idle, ยกเลิกงานเก่าเมื่อถูกแทรก และ log ที่เชื่อม input ID กับเวลารับรู้/ตัดสินใจ/ใช้คำสั่ง; RGB /255, คำสั่งมุมหน่วย rad |

## ประเด็นที่ช่วยแก้ปัญหาปัจจุบัน

Lab02 ลดความแกว่งจาก input ส่วน bounded_step ของ Lab06 จำกัดการเปลี่ยนเป้าหมาย: step = max_slew_rad_s × dt_s แล้วขยับจากค่าปัจจุบันไปหาเป้าภายใน step นี้ เป็นการจำกัดความเร็วของเป้าหมาย ไม่ใช่การรับรองความเร่ง/jerk หรือการเคลื่อนจริงของ servo

การทดลอง ID1 ล่าสุดใช้ goal หนึ่งครั้งต่อขา ร่วมกับ speed/acceleration ภายใน servo ผู้ใช้บอกว่าสมูทขึ้น จึงเก็บวิธีนี้เป็นฐานทดสอบ ก่อนตัดสินใจว่าจะเพิ่มการไล่เป้าจาก host หรือไม่ หลีกเลี่ยงการสร้างตัวไล่เป้าซ้อนโดยไม่มีผลเทียบ

bounded_step ของอาจารย์ใช้แกน semantic [tilt, extend, nod] 3 แกน ไม่ใช่ servo 5 ตัว และ bounds เป็นของแบบจำลอง ต้องกำหนด mapping ตามโครงจริงก่อนใช้ ห้ามยกค่า bounds หรือ max_slew ในแลปไปสั่งฮาร์ดแวร์โดยตรง

Lab02 safe_command=0 เป็นคำสั่งจำลอง ไม่ตีความว่าให้มอเตอร์จริงไปมุมศูนย์หรือปิด torque เมื่อ fault ระบบจริงคงหลักหยุด/ประคองเมื่อทำได้ตามที่ตกลง

สีและท่าจำลอง Lab06 ต่างจากแบบที่ผู้ใช้เลือกไว้ ใช้โครงสร้างการทำงานของอาจารย์ แต่รักษาสีและพฤติกรรมที่กลุ่มอนุมัติ ไม่แทนด้วยค่า default เงียบ ๆ

## ลำดับนำมาใช้

1. ใช้เครื่องมือกลางเดิมทดสอบฐานควบคุมข้ออื่นในช่วงที่ยืนยัน และการเคลื่อนร่วมกันก่อนอ้างว่าลื่นทั้งโคม
2. รักษา SensorFilter/FSM/log ของ Lab06–07 ที่ทำไว้; ใช้ Lab02 ตรวจการกรอง ToF และการสลับสถานะ โดยไม่เปลี่ยน threshold ของกลุ่มอัตโนมัติ
3. ผูกท่าที่ผู้ใช้ตรวจแล้วกับตัวสร้างเป้าหมาย โดยใช้หลักจำกัดการเปลี่ยนมุมของ Lab06 และประเมินร่วมกับ ramp ใน servo
4. เติมจังหวะจาก Lab03 และ AHM จาก Lab04–05 ตามการทดลองปรับเฉพาะ φ ที่ตกลง ไม่เพิ่มอัลกอริทึมใหม่เพื่อให้ดูเป็น Bio-Inspire
5. เชื่อม ROS/log ตาม Lab07; แยกเวลาสั่งคำสั่งออกจาก physical onset ที่ยังไม่ได้วัด

โมดูลที่ตรวจยังไม่มีตัวติดตามหน้าที่พร้อมใช้กับกล้องหัวโคม หรือ driver STS3215 สำหรับโครงจริงของเรา จึงยังมีช่องว่างฝั่งนี้ งานคณิตศาสตร์ยังต้องยืนยัน geometry/frame ของโครงจริงแยกจากสมการ AHM–CPG

## แหล่งอ้างอิงที่ตรึงเวอร์ชัน

- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_02/lab02.py
- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_03/README.md
- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_04/student_hormone.py
- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_05/course_model.py
- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_06/course_model.py
- https://github.com/potiwat/RAE67_bio_ins/blob/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_07/lamp_week07/bridge.py

