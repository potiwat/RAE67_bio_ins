# Protocol ที่ประกาศก่อนรัน Lab07 offline

วันที่: 26 ตุลาคม 2026; ยังไม่อ่านผล Lab07 เมื่อเขียน protocol นี้

คำถาม: composite delay/drop profile ของ Lab07 ส่งผลต่อการตอบสนอง FSM เดิมของกลุ่มและข้อมูล stale เทียบกับ ideal delivery อย่างไร

Prediction: C1 มี transport age/drop/out-of-order มากกว่า C0 อาจทำให้ fault ticks และ expected interactions ที่ไม่มี both onset เพิ่มขึ้น แม้ guarded filter จะเหมือนกันทั้งคู่ ไม่คาดว่าทุก event จะช้าขึ้นเท่ากันหรือ state transitions ต้องเปลี่ยนทิศทางเดียวกันเสมอ

ใช้ completed_policy.py จาก Lab06 กลุ่ม 7, 5 states และ positive mapping เดิม คง near/touch priority และ fallback ของอาจารย์

- C0: ideal delivery; delay 0, drop 0
- C1: profile ของอาจารย์ delay 0/.02/.04/.06/.10/.14/.18 s, random drop .08, burst drop 12.50–12.70 s
- สาม paired seeds 41/42/43 ใช้ source stimuli เดียวกันในแต่ละคู่; virtual trial 22 s, dt .02 s, scheduler .04 s
- filtering ใช้ guarded ทั้ง C0/C1, debounce .06 s, stale .12 s, bounds/slew/poses/RGB เดิมทั้งหมด
- expected set ประกาศล่วงหน้า: button_01, touch_01, approach_01, clear_01, near_01, clear_02, button_02 (7/trial)
- เก็บ all 10 source inputs รวม touch_conflict, invalid_01, stale_01 พร้อมเหตุผล ไม่เปลี่ยน denominator หลังเห็นผล
- response deadline ≤1 s; observation window ถึง 22 s; ทั้ง motion และ RGB ต้องมี onset จึงคำนวณ both latency ใช้เวลาที่ช้ากว่า ถ้าไม่ครบให้ null/ช่องว่าง/N/A ไม่แทน 0; พบครบแต่เกิน 1 s คือ deadline fail แยกจาก missing
- metrics หลัก: expected pass/7, missing/7, observed both latency; metrics ประกอบ transport age, dropped/out-of-order/censored, fault ticks/1101, state transitions
- รายงาน invalid/stale probes ที่ 11/12 s แยกในการอภิปรายจาก transport stress; C1 เปลี่ยน delay/drop พร้อมกันจึงสรุปเหตุแยกสองปัจจัยไม่ได้
- ทั้งหมดเป็น single-process virtual simulation ไม่มี ROS/DDS หรือ physical onset measurement

จะใช้ replay C1 seed 42 เทียบ input/command/events แบบ SHA256/byte-for-byte โดยไม่แก้ผลเดิม

แหล่ง: potiwat/RAE67_bio_ins commit fa528b169f1127ee3e0e9fae3d721546bf1b82d2, lab_07; policy กลุ่มจากสำเนาใน references/bio_inspire/group07_student_policy.py.txt
