# แหล่งต้นทางที่คัดเพื่อพัฒนาโคม

28ตุลาคม2026 — คัดให้Bio-Inspireเดินก่อน และเก็บkinematicsแยกสำหรับอีกวิชา

- ../../bio_inspire/docs/UPSTREAM_REUSE_REVIEW_TH.md: รายละเอียดใช้ส่วนไหน/ข้อจำกัด/ลำดับนำมาใช้
- ../../mathematical_robotics/reports/KINEMATICS_REFERENCE_REVIEW_TH.md: URDFและเครื่องมือคำนวณ พร้อมผลauditnominalmodel
- UPSTREAM_REUSE_CATALOG_20261028.json: รายการrepo/commit/license/ขอบเขต
- upstream/SOURCE_MANIFEST_20261028.json: ที่มา GitblobSHAและSHA256ของ14ไฟล์ที่เก็บจริง

ไฟล์Pythonอ้างอิงเก็บเป็น.py.txt และมีLICENSEตามต้นทาง ไม่ได้ติดตั้งหรือรันด้วยการเก็บไฟล์ การparseASTคือsyntaxcheck ไม่ใช่runtime/hardwaretest ค่าexampleทุกชนิดไม่ใช่ค่าของหุ่นผู้ใช้

LeLampmodelGPL-3.0แยกจากRuckigMIT, Picamera2examplesBSD-2-Clause, YuNetMITในโฟลเดอร์modelนั้น และRoboticsToolboxMIT เก็บต้นฉบับพร้อมที่มาไว้ เมื่อนำโค้ดไปปรับให้คงข้อความlicense/attributionที่เกี่ยวข้อง

lelamp_runtimeไม่มีLICENSEระดับrepoที่commitที่ตรวจ แต่READMEหัวข้อLicenseชี้ไปmainLeLamprepositoryที่มีGPL-3.0 และfollowerบางไฟล์มีApache-2.0header จึงเก็บข้อมูลcross-referenceและnoticeรายไฟล์ไว้ รอบนี้ยังไม่vendoranimation/CSVเข้ารันไทม์ โดยเลือกเริ่มจากตัวอย่างภาพ/trajectoryที่มีMIT/BSDLICENSEครบและไม่ผูกagent/voiceของruntimeทั้งชุด
