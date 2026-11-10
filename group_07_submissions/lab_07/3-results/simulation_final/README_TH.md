# Simulation ตาราง v2: ครบ6trials

P1/P2/P3 แต่ละคู่C0/C1 รันครบ600วินาทีจำลอง12000แถวต่อtrial ใช้inputตารางเดียวกับPi ค่าเริ่มHและoscillatorเหมือนกันทุกคู่ ใช้logical FSMที่พร้อมทันทีและSO2bankของruntime ไม่จำลองservo dynamics/camera/entrymotion เป็นdeterministicreplays ไม่ใช่อาสาสมัคร6คน

CSVทั้ง6ไฟล์และsummary.jsonมีhash, ตารางinput, parameter/sourcehash, M1frequency/ΔTรายepisode ผลนี้ยังไม่รับรองrealrobot

ช่วงInterested/Angryสั้นกว่าเวลาที่ต้องใช้วัดคาบครบ จึงได้N/AสำหรับM1/ΔTบางอารมณ์ ไม่ต่อข้ามstateเพื่อสร้างคาบปลอม ผลheld-statePCเดิมใช้แยกประกอบได้ แต่ไม่เติมแทนreal data รายงานต้องแยกcoverageของข้อมูลกับความเพียงพอของmetric
