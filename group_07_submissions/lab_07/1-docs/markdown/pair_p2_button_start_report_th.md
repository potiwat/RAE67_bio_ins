# เทียบ C0/C1 ชุดเริ่มด้วยปุ่ม5ครั้ง

คู่pilotจริง P2: C0=20261105T124439Z_db0023c1 และ C1=20261105T124913Z_86706a5d เก็บmetadata/summary/trace/diagnostic/metrics/rosbagและhashแล้ว ไม่ใช้คู่ก่อนหน้าที่จุดเริ่มไม่ตรงมาปน

| ผลตรวจ | C0 | C1 |
|---|---:|---:|
| ระยะข้อมูลจริง (s) | 81.118 | 82.305 |
| จำนวนแถว | 1017 | 1023 |
| FSM states | ครบ6 | ครบ6 |
| ปุ่มฐานทดลอง (ไม่รวม5เตรียม) | 1 | 1 |
| Touchทดลอง | 4 | 4 |
| FAULT / WAIT_TOF samples | 0 / 0 | 0 / 0 |
| Dropped / writer error / input health error | 0 / ไม่มี / ไม่มี | 0 / ไม่มี / ไม่มี |
| ROS topicsพบและcount/decodedhashตรง | 13 | 13 |
| Hเริ่ม | 0 | 0 |
| initial o1/o2 | −0.0269653308 / −0.5608626776 | เท่ากับC0 |
| initial phaseของbankทั้ง3ตัว (cycles) | 0.2576460133 | 0.2576460133 |
| initial model updates | 0ทุกตัว | 0ทุกตัว |

source_hashesที่บันทึกตรงกันทุกไฟล์ โปรไฟล์ต่างเฉพาะnormal_ahm_condition=C0/C1 ทุกค่าความเร็ว ความเร่ง PID ท่า และdecoderตรงกัน ไม่ได้ลดSpeedของC0หรือเพิ่มSpeedให้C1แยกกัน

## สิ่งที่เห็นจากข้อมูล

ทั้งคู่รับButton→Interested, Touch→Happy, TouchBurst→Angry, Near→Afraid, Clear→Normal และIdle→Sleepy จุดเริ่มที่ผู้ใช้กด5ครั้งแก้ปัญหาฮอร์โมน/เฟสเริ่มไม่ตรงกันของคู่pilotก่อนหน้าได้ในสองsessionนี้จริง

C0ใช้R=S และphi=0.10+0.03S จึงขึ้น/ลงตรงตามinputปัจจุบัน ช่วงNear phiขึ้นถึง0.13และกลับ0.10เมื่อSเป็น0 C1ใช้R=H ตามสูตรเดียวกัน phiสูงสุด0.128131แล้วค่อยลดตามฮอร์โมนหลังปล่อยinput ไม่ได้ล้างHเป็น0ทันทีเมื่อS=0 ตรวจสมการmappingจากทุกsnapshotคลาด0สำหรับทั้งสองcondition

ค่าสูงสุดของการเปลี่ยนphiระหว่างแถวติดกันคือC0=0.030000 และC1=0.005059 หน่วยrad/modelstep เป็นสถิติของพารามิเตอร์ที่sampled ไม่ใช่ตัววัดjerkหรือความสมูทเชิงกล และไม่ใช้ตัวเลขนี้สรุปผลเชิงเหตุผล เพราะinputจริงคนละจังหวะ/ความยาวและมีsnapshotgaps

รูป PAIR_P2_S_H_PHI.png และ PDF มาจากโคมจริงที่บันทึกsoftware state S/H/phi ไม่ใช่กราฟฮอร์โมนชีวภาพที่วัดจริง Sในรูปสร้างจากdebouncedGPIOsourceedgesร่วมกับNearที่sampledในowner เพื่อไม่ซ่อนpulseสั้นซึ่งกดและปล่อยครบระหว่างsnapshot ส่วนH/phiมาจากsnapshotตรงๆ ไม่เติมค่าพารามิเตอร์ระหว่างช่วงควบคุม

ข้อสังเกตด้านinputสั้น: บางButton/Touchเกิดครบระหว่างowner snapshots จึงเห็นHเพิ่มจากการreplaystableedges แม้Sปัจจุบันในแถวเป็น0แล้ว คำสั่งphiที่บันทึกของC0อาจกลับbaseก่อนsnapshot/การส่งคำสั่งรอบถัดไป ต้องไม่อ้างว่ากราฟSระดับownerที่ไม่เห็นpulseแปลว่าไม่มีinput หรืออ้างว่าความต่างนี้พิสูจน์C1เหนือกว่าโดยควบคุมเวลาทั้งสองไม่ตรงกัน

## ยังสรุปอะไรไม่ได้

- C1มีApproachอัตโนมัติประมาณ2sก่อนกดปุ่ม ส่วนC0มีApproachแทรกก่อนNearในช่วงท้าย เวลาและประวัติFSM/inputไม่ตรงกันทุกsample เป็นhumanpilotลำดับคล้ายกัน ไม่ใช่สิ่งเร้าเหมือนกันเป๊ะ
- ช่วงที่วัดo1ได้ต่อเนื่องและไม่maskedสั้น: C1Happyมี1คาบ (ประมาณ0.26434Hz); C0Happyและstateอื่นไม่มีคาบสมบูรณ์พอตามเกณฑ์แบ่งepisode ไม่มีstateใดมีคู่คาบติดกันสำหรับM2 ดังนั้นDeltaTเป็นN/A ไม่ใช่0
- snapshotgaps>0.5sอย่างละ3ช่วง ต้องตัดepisodeตรงช่องว่าง ไม่เชื่อมข้ามเพื่อสร้างคาบเพิ่ม
- ผู้ใช้Qจบก่อน180sตามที่ตกลง ทั้งคู่จึงคงsource.complete=falseและROSverification=INCOMPLETE แต่13topicsและcount/hashอ่านกลับตรง ข้อมูลไม่ได้หาย ไม่เปลี่ยนป้ายเป็นfinal600s3คู่

สรุปได้ว่าจุดเริ่มและการบันทึกระบบ6อารมณ์ใช้ได้ และC1แสดงการคงอยู่/ลดลงของฮอร์โมนในค่าจังหวะตามที่ออกแบบ ยังสรุปไม่ได้ว่าC1ทำให้มอเตอร์สมูทกว่าหรือM1/M2ดีกว่าC0

## หลักฐานและขั้นต่อไป

- PAIR_P2_BUTTON_START_COMPARISON.json: profile/source/init checks, events,sourcehashesและmetricsรายstate
- C0_bag_db0023c1/verification.json และ C1_bag_86706a5d/verification.json: ROS13
- compare_button_start_pair.py: สร้างJSONและPNG/PDFซ้ำได้ ใช้WSLpythonที่มีmatplotlib

รอบเก็บpilotคู่นี้เสร็จแล้ว ขั้นวัดถัดไปควรเป็นcomponent experimentที่ค้างstateพอให้มีหลายคาบ และ/หรือreplayสิ่งเร้าชุดเดียวกันบนคอมเพื่อแยกผลmappingจากเวลามนุษย์ ก่อนfinalหลายคู่ ไม่เปลี่ยนเวลาอารมณ์หรือค่ามอเตอร์ในโหมดเล่นโดยไม่แจ้ง ผู้ใช้ยังไม่ต้องทดลองเพิ่มระหว่างจัดขั้นวัดถัดไป
