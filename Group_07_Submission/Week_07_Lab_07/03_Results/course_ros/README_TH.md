# ROS 2 Jazzy · การรับส่งข้อความสามโหนดของ Lab 7

วันที่ 12 พฤศจิกายน 2026 เวลา 22:11–22:12 น. ตามเวลาประเทศไทย ได้รันสามโหนดบน WSL 2 และ Ubuntu 24.04 ด้วย ROS 2 Jazzy, Fast DDS, domain 87 และการค้นพบเฉพาะ `LOCALHOST` ตัวสร้างอินพุตใช้ seed 41 และนโยบายจาก `Lamp/Lab07/completed_policy.py` การสาธิตนี้วัดการส่งข้อความบนพีซี ส่วนผลจากโคมที่ใช้ Raspberry Pi 5 อยู่ใน [real_robot](../real_robot/)

## เส้นทางที่ค้นพบขณะรัน

| ต้นทาง → ปลายทาง | Topic | ชนิดข้อความ |
|---|---|---|
| `/week07_inputs` → `/week07_interaction` | `/lamp/input/button`, `/lamp/input/touch` | `std_msgs/msg/Bool` |
| `/week07_inputs` → `/week07_interaction` | `/lamp/input/distance` | `std_msgs/msg/Float32` (m) |
| `/week07_interaction` → `/week07_output_collector` | `/lamp/interaction`, `/lamp/emotion` | `std_msgs/msg/String` |
| `/week07_interaction` → `/week07_output_collector` | `/lamp/servo_command` | `std_msgs/msg/Float32MultiArray` ลำดับ tilt, extend, nod (rad) |
| `/week07_interaction` → `/week07_output_collector` | `/lamp/rgb_command` | `std_msgs/msg/ColorRGBA` ช่องสี 0–1 และ α = 1 |

พบจุดเผยแพร่และรับจากสามโหนดหลัก 14 จุด และจุดรับของ `/rosbag2_recorder` อีก 7 จุด ผู้สังเกตกราฟบันทึกชื่อโหนด ชนิดข้อความ และ GID ของแต่ละจุด Fast DDS รายงาน `RELIABLE` และ `VOLATILE` ทุกจุด ส่วน history/depth ที่ถามผ่านเครือข่ายคืนค่า `UNKNOWN/0` โค้ดของโหนดกำหนด `KEEP_LAST` และ depth 10 [จุดเชื่อมต่อที่สังเกต](observed_endpoints.csv) · [ภาพรวมกราฟที่บันทึก](observed_graph.json)

## ผลที่วัดได้

| กลุ่ม topic | ส่งต่อ topic | ปลายทางรับต่อ topic | bag เก็บต่อ topic |
|---|---:|---:|---:|
| อินพุต 3 topic | 1,101 | 1,098 | 959 |
| เอาต์พุต 4 topic | 1,140 | 1,137 | 1,137 |

โปรโตคอลกำหนด 1,101 เฟรม ตั้งแต่ 0.00 ถึง 22.00 วินาที นาฬิกาบนเครื่องวัดระหว่างบรรทัดเผยแพร่อินพุตแรกกับสุดท้ายได้ 22.0012 วินาที โหนด interaction ทำงานก่อนเริ่มและหลังสิ้นสุดสัญญาณต้นทาง จึงมีจำนวนรอบส่งเอาต์พุตต่างจากจำนวนเฟรมอินพุต ตัวรับเห็นสถานะ Normal 519 ครั้ง, Interested 268, Happy 96, Afraid 100 และ Sleepy 154 [จำนวนข้อความต่อ topic](message_counts.csv) · [ผลตรวจทั้งรอบ](verification.json)

เริ่ม collector แล้วเปิด recorder ตามด้วย interaction รอจนค้นพบ subscription ของ recorder ครบเจ็ด topic ก่อนเปิด inputs หลักฐานการพร้อมบันทึกเกิดก่อนการเผยแพร่อินพุตแรก 281.047 ms รวมใน bag 7,425 ข้อความ ทั้งเจ็ด topic อ่านกลับจาก SQLite และถอดรหัส CDR ได้ครบ ข้อมูลที่ bag เก็บน้อยกว่าที่ต้นทางส่ง 142 ข้อความต่ออินพุต ในบันทึกของ interaction มีอินพุตน้อยกว่าที่ต้นทางส่ง 3 ข้อความต่อ topic ข้อความในสัญญารายวิชาไม่มี Header หรือเลขลำดับจากต้นทาง จึงระบุตัวอย่างที่ขาดแต่ละตัวจาก bag เพียงอย่างเดียวไม่ได้ และไม่มีค่าความหน่วงจากเซนเซอร์ถึงการเคลื่อนจริง [ข้อมูล bag](bag_info.txt) · [ตัวอย่างข้อความที่ถอดรหัส](message_samples.json)

บันทึกรายโหนดมี 3,303 แถวจาก inputs, 7,854 แถวจาก interaction และ 4,548 แถวจาก collector เวลาแต่ละบรรทัดเป็น `perf_counter_ns` บนโฮสต์เดียวกัน [inputs.csv](inputs.csv) · [interaction.csv](interaction.csv) · [collector.csv](collector.csv)

## ซอร์สที่ใช้และการแก้หนึ่งบรรทัด

ตรวจไฟล์แพ็กเกจ 10 ไฟล์เทียบ Git blob ของ commit `fa528b169f1127ee3e0e9fae3d721546bf1b82d2` ก่อน build เมื่อใช้ไฟล์อาจารย์โดยตรง Jazzy ส่ง `Float32MultiArray.data` ออกมาเป็น `array.array` และตัวเขียน CSV เรียก `json.dumps` แล้วเกิด `TypeError` ก่อนเริ่ม inputs รอบที่วัดผลใช้ `list(servo.data)` สำหรับ payload ของ CSV การเรียกเผยแพร่ไปยัง DDS ยังส่งวัตถุข้อความเดิม ตรวจ CDR ของข้อความทดสอบก่อนและหลังอ่านค่าไปเขียน CSV ได้ SHA-256 เดียวกัน นโยบายกลุ่มมี SHA-256 `2a7d07a3cf685a248becc075cb23c06e8bbe7af41631ccf6cb23d8e8cc16159c` [ซอร์สรายวิชา ณ commit ที่ใช้](https://github.com/potiwat/RAE67_bio_ins/tree/fa528b169f1127ee3e0e9fae3d721546bf1b82d2/lab_07) · [รายการ SHA](reproduce/source_provenance.json) · [ข้อผิดพลาดเดิม](compatibility/original_jazzy_exception.txt) · [diff](compatibility/jazzy_trace.patch) · [แฮชไฟล์ที่รัน](compatibility/source_change.json) · [ผลทดสอบ CDR](compatibility/wire_check.json)

## ตรวจหรือรันซ้ำ

จากโฟลเดอร์ `course_ros` ใน Ubuntu 24.04 ที่ติดตั้ง ROS 2 Jazzy, rclpy, std_msgs, rosbag2-sqlite3 และ colcon แล้ว คำสั่งต่อไปนี้ตรวจไฟล์ที่ส่งและเก็บผลตรวจในพื้นที่ชั่วคราว

```bash
source /opt/ros/jazzy/setup.bash
qa_dir="$(mktemp -d)"
python3 -B reproduce/verify_recording.py . --output "$qa_dir"
cmp verification.json "$qa_dir/verification.json"
```

หากต้องการวัดรอบใหม่ ใช้คำสั่งด้านล่าง สคริปต์คัดซอร์สที่แนบไปยัง workspace ใหม่ แก้บรรทัด CSV ทดสอบชนิดข้อความและ CDR แล้วเก็บสาม trace, graph และ bag ใต้โฟลเดอร์ `session/` ของรอบนั้น จำนวนข้อความที่รับจริงอาจเปลี่ยนตามจังหวะการค้นพบ DDS และเวลาทำงานของเครื่อง

```bash
bash reproduce/run.sh /tmp/lab07_course_new_run
```
