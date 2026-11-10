# งานต้นทางที่นำมาช่วยให้ Bio-Inspire เสร็จเร็วขึ้น

อัปเดต 29 ตุลาคม 2026: ผู้ใช้ให้ยึดแลปอาจารย์ก่อน อ่าน TEACHER_LAB_REUSE_MAP_TH.md ข้อเสนอ Ruckig ด้านล่างเก็บเป็นประวัติ/ทางเลือก ยังไม่เลือกติดตั้งหรือใช้แทน bounded_step และตัวเร่งภายใน servo โดยอัตโนมัติ

ตรวจ 28 ตุลาคม 2026 — เน้นคัดส่วนที่ใช้ได้จริงและแยกสิ่งที่ยังไม่ผ่านการลองบนPi ไม่มีการติดตั้ง รันสคริปต์ต้นทาง หรือส่งคำสั่งมอเตอร์จากงานค้นครั้งนี้

## ข้อเสนอที่ช่วยให้งานเดินเร็ว

ใช้ฐานFSMและAHM–SO(2)CPGของกลุ่ม/อาจารย์ที่ตกลงแล้ว ร่วมกับตัวอย่างกล้องทางการและตัวสร้างtrajectoryที่มีอยู่ แยกการทดสอบภาพกับการเคลื่อนก่อนรวม เป้าคือเลิกเขียนทุกชั้นจากศูนย์และลดการพึ่งโครงการใหญ่ที่มีเสียง/LLM/การฝึกโมเดลซึ่งไม่อยู่ในงานขั้นต่ำ

ชุดแรกที่แนะนำให้ทดลอง: Picamera2 face exampleสำหรับภาพ และRuckig Communityแบบstate-to-stateสำหรับประเมินการเคลื่อนนุ่ม โดยเลือกค่ามุม/velocity/acceleration/jerkจากโครงจริงร่วมกับผู้ใช้ ไม่หยิบตัวเลขในตัวอย่างมาสั่งหุ่น

## 1 LeLamp ต้นทางที่ตรงฮาร์ดแวร์ที่สุด

- [Runtime](https://github.com/humancomputerlab/lelamp_runtime/tree/ee23699075fc3d3154da86a71c38a024545b6785)
- [AnimationService](https://github.com/humancomputerlab/lelamp_runtime/blob/ee23699075fc3d3154da86a71c38a024545b6785/lelamp/service/motors/animation_service.py)
- มีrecordingsชื่อcurious, happy_wiggle, scanning, wake_up และตัวบริการevent/playbackที่รองรับการขัดจังหวะและinterpolationเข้าท่าแรก (ตรวจจากtreeและsourceจริง)
- ใช้เป็นตัวอย่างการแยกmotionservice/eventและการประกอบท่าทาง ปรับแนวคิดให้เข้ากับstate/CPGของเรา ไม่ใช้recordedclipแทนผลAHM–CPG
- followerตรงกับSTS3215 ID1–5และชื่อข้อที่กลุ่มใช้ จึงเป็นแหล่งเทียบdriverที่เกี่ยวข้อง

ข้อที่พบจากsourceและต้องไม่รันทั้งชุดทันที:

1. connect(calibrate=False)ยังเรียกconfigure() ซึ่งปิดtorqueชั่วคราว ตั้งOperating_Mode และเขียนP/I/D ไม่ได้หมายถึงเชื่อมแบบไม่เปลี่ยนมอเตอร์
2. disconnectใช้disable_torque_on_disconnectตามconfig ซึ่งต่างจากความต้องการหยุดประคองของกลุ่ม
3. animationserviceเริ่มเล่นidleตอนstart; เมื่อยังไม่มี_current_stateจะไม่ตั้งinterpolationจากfeedbackปัจจุบันก่อนframeแรก จึงยังต้องออกแบบstartupของเราเอง
4. interpolationในไฟล์ไม่ได้มีสัญญารับรองvelocity/acceleration/jerk และไม่ใช่หลักฐานว่าทุกtransitionของโครงเราจะสมูท
5. smooth_animation.pyเป็นdemoที่ผูกLiveKit/LLM/เสียง ไม่ใช่ตัวแก้smoothmotorล้วน ไม่ควรติดตั้งdependencyทั้งprojectเพื่อทำmotionพื้นฐาน
6. ค่าในCSVขึ้นกับcalibration/ท่าของเจ้าของ ไม่ใช่ค่าข้อต่อที่ผู้ใช้อนุมัติ

ไลเซนส์: ที่commitที่อ่านไม่พบLICENSEระดับrepoและGitHubmetadataเป็นnull แต่READMEหัวข้อLicenseชี้ไปmainLeLamprepositoryซึ่งมีGPL-3.0 ขณะที่followerมีApache-2.0headerรายไฟล์ จึงบันทึกตามหลักฐานว่าREADMEอ้างGPL-3.0และมีnoticeรายไฟล์ต่างกัน ไม่เรียกทั้งrepoว่าMIT/Apache-2.0โดยอัตโนมัติ รอบนี้ใช้animation/recordingsเป็นแนวทางและยังไม่vendoredเข้ารันไทม์ ตัวอย่างที่นำมาเก็บสำหรับเริ่มงานภาพ/trajectoryเลือกMIT/BSDที่มีLICENSEติดไฟล์มาครบ

## 2 Ruckig สำหรับฐานการเคลื่อนสมูท

- [SourceและREADME](https://github.com/pantor/ruckig/tree/99751e6ebc7c963bb80e99fbbe66f2c279d1db57)
- [ตัวอย่างPython state-to-state](https://github.com/pantor/ruckig/blob/99751e6ebc7c963bb80e99fbbe66f2c279d1db57/examples/01_position.py)
- ตัวสร้างtrajectoryจากcurrent/targetposition, velocityและacceleration ภายใต้velocity/acceleration/jerklimits เป็นฐานที่เกี่ยวกับความสมูทโดยตรง มีPythoninterfaceและMITlicense
- เก็บตัวอย่างและLICENSEที่shared/references/upstream/ruckig/99751e6ebc7c963bb80e99fbbe66f2c279d1db57/แล้ว

ขอบเขตที่เลือกพิจารณา: Community state-to-stateที่คำนวณlocal ไม่ใช้intermediate_positionsที่Communityส่งคำนวณcloud และไม่ถือว่าTracking interfaceของProเป็นของฟรี ต้องมีตัวตรวจjoint/pathlimitsของเราเอง

การใช้กับงาน: เริ่มประเมินช่วงเข้า/ออกposeและการเปลี่ยนท่าในsoftwareก่อน ไม่เอาRuckigแทนSO(2)CPG และไม่สมมติว่าการส่งเป้าCPGผ่านplannerทุกframeจะรักษาความถี่/เฟสเดิม ต้องวัดphase lagและการlimitแยกหากเลือกวิธีนี้

ต้องตรวจPython/ARMbuildและการส่งเป้าร่วมกับตัวrampในservoบนเครื่องจริงก่อนอ้างว่าใช้ได้ ยังไม่ติดตั้งบนPiและยังไม่รับรองphysicalsmoothnessจากกราฟtrajectoryเพียงอย่างเดียว

## 3 Picamera2 และ OpenCV สำหรับภาพกับการมองตาม

- [Raspberry Pi example](https://github.com/raspberrypi/picamera2-examples/blob/d25baef2f4aedd8159ceafd5d8299918aaf9eeee/examples/opencv_face_detect_2.py) — BSD-2-Clause
- [OpenCV YuNet](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet) — LICENSEในโฟลเดอร์นี้เป็นMIT ต่างจากLICENSEระดับrootOpenCVZooที่เป็นApache-2.0
- เก็บsourceexample, YuNetwrapper/demo และLICENSEทั้งสองไว้แล้ว โดยยังไม่ดาวน์โหลดmodelweight

Picamera2exampleแสดงวิธีอ่านCSIcamera/ภาพloresและตรวจกรอบหน้า เหมาะเป็นจุดเริ่มที่สั้นและตรงPiกว่าโค้ดPiCameraเก่า ส่วนYuNetเป็นอีกdetectorให้เลือกหลังตรวจOpenCV/modelversionและภาพจริง ไม่จำเป็นต้องติดตั้งทั้งสองแบบพร้อมกันหรือเพิ่มMediaPipeก่อนรู้ว่าจำเป็น

สิ่งที่ยังต้องทำเฉพาะงานเรา: เลือกหน้าใกล้กลางภาพตอนเริ่มที่Normal ยึดผู้เล่นเดิม เลือกกติกาหน้าหาย/ค้นหาโดยไม่รีเซตidle กรองความไม่นิ่งของภาพ และส่งผลผ่านmotiondecoderเดียวกับอารมณ์ ตัวตรวจกรอบหน้าไม่มีหน้าที่สั่งservo5ตัวเอง

## 4 Cornell Pixar Lamp งานที่คล้ายในระดับระบบ

- [โครงงานCornellปี2019](https://courses.ece.cornell.edu/ece5990/ECE5725_Fall2019_Projects/Dec_04_Demo/Pixar_Lamp/Website/index.html)
- เป็นตัวอย่างface-trackinglampและการเรียกroutineแสดงท่าทาง เหมาะดูworkflowภาพ→facecentererror→การหัน→routine
- โค้ดที่แสดงใช้VideoStream(usePiCamera=True)รุ่นเก่า และserialframeขึ้นต้น0x55ซึ่งต่างจากSTSของเรา ไม่ใช้แทนPicamera2หรือUARTdriverปัจจุบัน
- ตัวอย่างเลือกหน้าจากพื้นที่ใหญ่สุด ต่างจากกติกาใกล้กลางภาพและยึดคนเดิมของกลุ่ม
- ยังไม่ยืนยันไลเซนส์คัดลอก ใช้เป็นแนวทางและที่มาในรายงาน ไม่ได้คัดsourceของเว็บมารัน

## 5 ELEGNT ของApple สำหรับออกแบบการแสดงอารมณ์

- [ELEGNT — Apple Machine Learning Research](https://machinelearning.apple.com/research/elegnt-expressive-functional-movement)
- งานแบ่งการเคลื่อนที่มีหน้าที่กับการสื่อเจตนา/ความสนใจ/อารมณ์ ใช้movementprimitivesและinteractionstoryboards เหมาะอ้างอิงว่าทำไมท่าทาง+gazeสำคัญกับโคมที่ไม่มีใบหน้า
- ใช้ช่วยวางการทดลองให้ผู้เล่นสังเกตพฤติกรรมและออกแบบคลิปตัวอย่างก่อนรัน ไม่ใช่คำสั่งให้เพิ่มLLMหรือฝึกโมเดล
- หน้าที่ตรวจเป็นงานวิจัย/วิดีโอ ยังไม่ได้ให้implementationพร้อมใช้กับ5STSของเรา และไม่ได้แทนข้อกำหนดAHM–CPGในรายวิชา

## 6 งานAHM–CPGที่เกี่ยวข้องโดยตรง

- [Online Gait Adaptation of a Hexapod Robot Using an Improved Artificial Hormone Mechanism](https://www.manoonpong.com/paper/2018/SAB2018_paper_34.pdf) — Potiwat Ngamkajornwiwat, Pitiwut Teerakittikul และPoramate Manoonpong
- มีการเชื่อมhormone/receptorกับการควบคุมความถี่CPG จึงใช้เป็นพื้นฐานแนวคิด/แหล่งอ้างอิงที่เกี่ยวข้องได้
- เป็นงานhexapodในsimulation มีสมการ/พารามิเตอร์เฉพาะงานนั้น ไม่คัดค่ามาแทนEuler/tanh/φmappingของLab03–05ที่กลุ่มตกลงแล้ว ไม่มีการอ้างว่าcoursemodelคือสมการเดียวกับpaperทุกข้อ

## แผนใช้ของที่มีเพื่อให้งานเดินเร็ว

| ลำดับ | ส่วนที่ใช้ | ผลงานที่ควรได้ก่อนรวม |
|---|---|---|
| 1 | driverเดิมที่อ่าน/ส่งเป้าตรงได้ + ศึกษาRuckig | ทดลองtrajectoryบนsoftwareและตรวจphysicalstart/stopในช่วงที่ผู้ใช้เลือก |
| 2 | Picamera2example และdetectorที่เข้ากับenvironmentจริง | ภาพที่ระบุผู้เล่นได้ ไม่สั่งมอเตอร์ |
| 3 | motioncontrollerเดียว + gazeที่ผ่านการสอบเทียบแกน | Normalตามหน้าและค้นหาได้ลื่นในช่วงที่ตรวจ |
| 4 | statebehaviorที่ผู้ใช้เลือก + SO(2)CPG/AHMเดิม | interested/happy/afraid/sleepyพร้อมgazeและสีที่ตรวจจริง |
| 5 | protocolC0/C1ตามworksheet | หลักฐานทำซ้ำ/CSVและอัปเดตรายงาน |

การใช้งานต้นทางไม่ตัดขั้นตอนเลือกworkingrange/ท่า/หน่วยบนโครงเรา และไม่ทำให้คุณภาพการเคลื่อนผ่านโดยอัตโนมัติ เป้าคือลดโค้ดที่ต้องคิดใหม่และใช้เวลาทดสอบให้ตรงจุด

## สิ่งที่ไม่เพิ่มเพื่อเร่งงาน

ไม่เพิ่มvoiceassistant/LLM, reinforcementlearning, GPU/cloudinferenceหรืออารมณ์เพิ่มจากการเห็นdemoของคนอื่น ไม่เปลี่ยนFSM/สมการ/ค่าทดลองกลุ่ม และไม่รันcalibratorที่เขียนEEPROMโดยอัตโนมัติ

## หลักฐานและไฟล์ที่เก็บ

shared/references/UPSTREAM_REUSE_CATALOG_20261028.jsonแยกรายrepo/ไลเซนส์/วัตถุประสงค์ และshared/references/upstream/SOURCE_MANIFEST_20261028.jsonระบุcommit, sourcepath, GitblobSHA, SHA256ของ14ไฟล์ที่เก็บจริง Sourceที่เป็นPythonเก็บนามสกุล.py.txt เพื่อไม่ให้สับสนกับruntimeที่ต้องรัน มีLICENSEอยู่ด้วย

ผลตรวจครั้งนี้เป็นsource reviewและsyntax parse ไม่ใช่ผลรันกับdependencyหรือหุ่นจริง
