# วิธีอ่าน CSV สำหรับตรวจงาน

CSV ต้นฉบับอาจารย์อยู่ใน results/group07_offline_20261026/<condition>_r<repeat> ไม่แก้ไฟล์ผลเดิม

- input_trace.csv: source/sample/publish/receipt, ค่า input, planned delay/drop และ accepted/out-of-order/censored
- command_trace.csv: เวลา tick, interaction, emotion, fault, tilt/extend/nod rad และ RGBA 0..1 เป็นคำสั่งที่ apply ใน software model ไม่ใช่ feedback มอเตอร์
- events.csv: candidates, state ก่อน/หลัง, decision/queued/applied/onset/status; new_state ว่างใน held/discarded ไม่ได้หมายถึง state หาย
- metrics.json: source_outcomes ทั้ง 10 inputs และ expected set 7; null หมายถึงวัด onset ไม่ครบ

CSV รวมที่เพิ่มสำหรับอาจารย์อ่านอยู่ใน review_csv/*_trace_7topics.csv มีหัวคอลัมน์ครบทั้งเจ็ด /lamp/... topics พร้อม time_s, state_before, fault และ decision_events_json

ค่า input ใน CSV รวมเป็น latest accepted receipt ที่ engine เห็นใน tick นั้น ไม่ใช่เอา source ล่าสุดที่ยังมาไม่ถึงมาย้อนใส่ input แต่ละช่องมี sample/source/receipt time, sequence และ input_id แยกกัน ค่าเริ่มต้นยังไม่เคยรับ sample เป็นช่องว่าง; NaN ที่รับจริงยังคงเป็น NaN ไม่แปลงเป็นระยะ 0

servo_command เก็บ JSON array ตามลำดับ [tilt,extend,nod] หน่วย rad; rgb_command เก็บ [r,g,b,a] ช่วง 0..1 และ alpha=1 ค่าปุ่มและสัมผัสเป็น logical 0/1 ของ simulator ไม่ใช่แรงดัน GPIO จริง

decision_events_json เป็นข้อมูล event ที่ตัดสินใจใน tick นั้นพร้อมผลสุดท้ายตลอด trial จึงมี onset ในอนาคตได้ ไม่ใช่ข้อมูลที่ controller รู้ล่วงหน้า ถ้าต้องการตรวจ pending ณ เวลานั้น ให้ดู queued/applied/first_motion/first_rgb timestamps เทียบ time_s; status ที่บันทึกเป็น final status ไม่ใช่ live queue snapshot

เมื่อ state เปลี่ยนแล้ว output ยังรอ scheduler สี/ท่าในแถวนั้นอาจยังเป็นคำสั่งของ state ก่อนหน้า นี่เป็นเหตุให้ต้องแยก state time กับ output time ไม่บังคับให้ตรงกันทุกแถว

physical_motion_onset_s / physical_rgb_onset_s เว้นว่างทั้งหมด เพราะยังไม่ได้วัดจริง ข้อมูลจำลองไม่ใช้แทน physical latency

metrics_summary.csv รวม 6 trials; source_outcomes_all.csv เก็บ 60 source outcomes พร้อม primary_expected_both เพื่อไม่ตัด misses ออก manifest ของ CSV รวมแยกจาก manifest ต้นฉบับ
