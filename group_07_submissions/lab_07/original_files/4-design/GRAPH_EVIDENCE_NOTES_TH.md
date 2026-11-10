# Graph ในชุดส่งงาน

ผู้ใช้อนุมัติรูปแบบใหม่และให้ใส่แทนข้อความแล้ว: LeLamp_Architecture.png พร้อม SVG/Draw.io แยกขอบเขต Pi / WSL / Simulation กล่องบน Pi เป็น functional blocks ไม่ใช่ ROS nodes แยกกัน; ภาพ ROS replay อยู่ภาคผนวก

คงภาพต้นฉบับผู้ใช้ ROS_Replay_rqt_graph_USER_20261106.png: rosbag2_player → 13 topics ใต้ /lamp ไม่มี subscriber ในภาพ /events/read_split เป็น topic ของ rosbag ไม่นับใน 13 รายการ เป็น replay ไม่ใช่ live control บน Pi

Pi ใช้ UART owner เดียวควบคุม STS3215; FSM/AHM/CPG เป็นส่วนภายในโปรแกรม ไม่ใช่ ROS nodes แยก ไม่มี ROS actuator subscriber หรือ MCU/micro-ROS Agent แยก Simulation เป็น logical FSM/AHM/CPG ไม่ใช่กลศาสตร์เซอร์โว/กล้อง

ข้อกำหนด scenario คน10นาทีไม่ได้ระบุว่าคลิปต้องยาว10นาที ชุดจริง600sใช้ scripted inputs และคนอยู่หน้ากล้อง ระบุวิธีจริงไม่อ้างว่าคนกดทุกเหตุการณ์เอง
