# เตรียมอัป GitHub

ชุดส่งอยู่ในเครื่อง ยังไม่ได้ commit/push หรือส่งให้อาจารย์

1. ใช้ README.md และ WORD_FILES_INDEX_TH.md เลือกเอกสารหลัก ใบงาน/Proposal/สรุปปรับตามหลักฐานแล้ว
2. วางเนื้อหาในโฟลเดอร์ Week_07_Lab_07 ของ repository ที่จะส่ง โดยคง relative paths
3. รัน `python verify_package.py` ตรวจ SHA256; ผลนี้ตรวจความครบของไฟล์ ไม่ใช่การรับรองคะแนน
4. เก็บ raw/config/source snapshot และผลที่มี misses/hold/N/A ตามเดิม อย่าเปลี่ยน pilot INCOMPLETE เป็น final
5. คลิปอยู่ 07_Evidence/คลิปทดลองเล่น.mp4 ตรวจขนาดไฟล์และข้อจำกัด GitHub ก่อนอัป หากใช้ลิงก์ภายนอกให้ผู้ใช้ตรวจสิทธิ์เข้าถึง
6. ถ้าแก้เอกสารภายหลัง ต้องสร้าง manifest/ZIP ใหม่ ห้ามแก้ raw เพื่อให้ผลดูดีขึ้น

ROS บน WSL มีทั้ง teacher three-role runs, replay และ live observation ของ Pi แยกหลักฐานกัน Pi 5 ควบคุมโคมโดยตรงและส่งข้อมูลผ่าน SSH ไป WSL ไม่มี ROS actuator subscriber บน Pi ไม่มี MCU แยกหรือ micro-ROS Agent
รอบหุ่น 600 วินาทีใช้ scripted inputs ขณะผู้ใช้นั่งหน้ากล้อง ไม่ใช่คนกดเล่นทุกเหตุการณ์ Simulation เป็น logical model ไม่มี servo/camera dynamics
