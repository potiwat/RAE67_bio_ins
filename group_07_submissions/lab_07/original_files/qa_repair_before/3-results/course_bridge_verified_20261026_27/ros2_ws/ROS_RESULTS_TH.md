# ผล ROS2 Lab07 หลังแก้ logging — 27 ตุลาคม 2026

## สิ่งที่แก้

ผู้ใช้อนุมัติแก้เฉพาะ logging payload ของ servo จาก `servo.data` เป็น `list(servo.data)` เพื่อให้ json.dumps เขียน CSV ได้ สำเนาที่แก้อยู่ src/lamp_week07/lamp_week07/ros_nodes.py ต้นฉบับยังอยู่ ../lamp_week07/ros_nodes.py ตัวตรวจยืนยันว่าต่างกันเพียงจุดนี้ ไม่เปลี่ยน message ที่ publish, FSM, amplitude, thresholds, timing หรือ QoS

## สิ่งที่รันจริง

Ubuntu24.04 บน WSL2, ROS2 Jazzy, Python3.12.3 ใช้ policy Lab06 เดิม เปิด synthetic_inputs, interaction และ output_collector เป็นคนละprocess และเปิด rosbag ก่อน inputs ตามคู่มือ ไม่ติดตั้งแพ็กเกจเพิ่ม

รันสามรอบด้วยseeds41/42/43 source protocol22sของอาจารย์ครบทุกครั้ง ค่าเริ่มต้นทั้งหมดจากชุดอาจารย์ ไม่มีการฉีดC1 delay/dropเข้าROS2 จึงแยกผลนี้จากoffline C0/C1ที่เคยรันแล้ว

| รอบ/seed | inputsบันทึกว่าส่งต่อchannel | interactionรับต่อchannel | พบ5statesครบ | receipt-staleกลับnormal |
|---|---:|---:|---|---|
| 1/41 | 1101 | 1101 | ครบ | พบ |
| 2/42 | 1101 | 1101 | ครบ | พบ |
| 3/43 | 1101 | 1101 | ครบ | พบ |

พบnormal/interested/happy/afraid/sleepyครบในcollectorของแต่ละรอบ ตรวจหน่วยservoเป็นradและvector3แกนตามcontract และRGBAอยู่0..1 alpha1 ตรวจไม่เกินsemantic boundsของmodel ไม่ได้ใช้ผลนี้รับรองช่วงปลอดภัยservoจริง

## การบันทึกและข้อจำกัด

CSV inputs/interaction/collectorรวมข้อมูลครบเจ็ดtopics: button,touch,distance,interaction,emotion,servo_command,rgb_command แต่จำนวนข้อความในbagไม่เท่าจำนวนที่publishในlogทุกtopic

| seed | bag button | bag touch | bag distance | sourceแต่ละchannel |
|---|---:|---:|---:|---:|
| 41 | 1096 | 1099 | 1095 | 1101 |
| 42 | 1097 | 1096 | 1097 | 1101 |
| 43 | 1096 | 1094 | 1095 | 1101 |

เก็บความต่างนี้เป็นผลจริง ไม่เติมข้อความที่ขาดและไม่สรุปว่าเกิดnetworkdropจากจำนวนอย่างเดียว การlog publishเป็นattemptก่อนส่ง ขอบเขตเริ่มบันทึก/การค้นพบendpointต่างกันได้ ไม่มีidentityบนwireเพียงพอให้จับคู่ทุกข้อความย้อนหลังตามordinal

QoSในโค้ดอาจารย์คงRELIABLE, KEEP_LAST depth10, VOLATILE; graphตรวจreliability/durabilityได้ แต่รายงานhistory=UNKNOWN/depth=0 จึงเก็บเป็นค่าที่ตรวจไม่ได้ ไม่เปลี่ยนให้ดูเหมือนวัดได้10 ประเด็นนี้มีบันทึกที่ https://github.com/ros2/rmw_fastrtps/issues/684

`source_latency_s`ในCSVยังว่างทุกแถว; physical latency เป็นN/A/null เพราะไม่ได้วัดจริง ไม่หักเวลาsourceข้ามnodeจากข้อมูลที่ไม่มีHeader อินพุตสังเคราะห์stale sampleของofflineไม่ได้ส่งacquisitiontimeบนBool จึงแยกจากreceipt-staleที่ทดสอบROS

## ไฟล์หลักฐาน

- logs/course_ros_20261027_loggingfix_attempt2_r01 ถึง r03: inputs.csv, interaction.csv, collector.csv, graph, metadata, stdout, bag_info และreceipt_stale_observation
- bags/ชื่อรอบเดียวกัน: rosbag MCAP + metadata
- ROS_VERIFICATION.json: ผลตรวจและSHA256ของหลักฐาน
- ROS_JAZZY_LOGGING_FIX_REVIEW.patch: diffที่ผู้ใช้อนุมัติ
- เก็บรอบที่ล้มก่อนแก้และรอบที่ตัวตรวจหยุดแยกไว้ ไม่เอามานับเป็น3รอบสำเร็จ

Lab07ยังไม่เสร็จทั้งหมด: ช่องproposalที่ต้องเลือกเองยังต้องถามผู้ใช้, AHM/CPG integrationยังเป็นงานที่ไม่ได้implement, ยังไม่มีphysical calibration/robot trial600s ไม่มีการเชื่อมPiหรือขยับมอเตอร์ในงานรอบนี้
