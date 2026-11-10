# LeLamp Experimental Results for Canva

## ขอบเขตที่ใช้

ใช้ Normal controlled hardware pilot `normal_controlled_20261104/comparison_r01` เพียงคู่เดียว: `c0_r01` และ `c1_r01` รอบละ50วินาที เก็บวันที่4พฤศจิกายน2026 ชุดนี้เตรียมตามสถานะโครงการ4–5พฤศจิกายน ไม่รวม Happy/Angry หรือชุด600วินาทีรุ่นใหม่

เป็น **Hardware pilot with recorded-input replay**: มอเตอร์/encoderเป็นของโคมจริง ส่วน S มาจาก inputจริงR08ช่วง80–130sที่นำมาreplay; H/φ/o1เป็นสถานะโมเดลที่runtimeบันทึก ไม่ใช่เซนเซอร์ฮอร์โมน และไม่เรียกชุดนี้ว่าSimulation

## ไฟล์พร้อมใช้ใน Canva

| กราฟ | PNG หลัก | CSV |
|---|---|---|
| 1 φ ตามเวลา | PNG/01_C0_C1_Phi.png | CSV/01_phi_C0.csv และ01_phi_C1.csv |
| 2 Command/Encoder ID2 | PNG/02_ID2_Command_Feedback.png | CSV/02_motor_ID2_C0.csv และ02_motor_ID2_C1.csv |
| 3 S/H | PNG/03_Stimulus_Hormone_C1.png | CSV/03_stimulus_hormone_C1.csv |
| 4 Period/ΔT | PNG/04_CPG_Period_DeltaT.png | CSV/04_cpg_periods_C0.csv และ04_cpg_periods_C1.csv |

PNG ทุกกราฟใช้ชื่อแกน/legendภาษาอังกฤษ ความละเอียด3840×2160px (300dpi). กราฟมอเตอร์มีC0/C1คนละpanelและPNGแยกให้เลือกใช้เพิ่ม CSVเป็นUTF-8 BOM ค่าทศนิยมเต็ม ไม่มีการเติมtimeseriesใหม่

นำCSVเข้าCanvaแยกแต่ละcondition ใช้Timeเป็นแกนXตามตัวเลขจริง ไม่วางC0/C1ทับกันด้วยหมายเลขแถว `01_phi_long_timeseries.csv` เป็นไฟล์รวมแบบlongที่คงTimeของแต่ละcondition ไม่ใช่ข้อมูลจับคู่แถว

## เวลาและหน่วย

- กราฟ1–3: Time = owner CLOCK_BOOTTIME − measurement.started_s ของconditionนั้น เริ่มต้นแต่ละรอบที่t=0 (652/659แถว) เวลาบันทึกจริงไม่ตรงกัน ห้ามอ้างว่าคำสั่งใช้พร้อมกันทุกsample
- S/H/φเป็นค่าที่บันทึกในsnapshot AHM selection time/schedule indexแยกไว้ในCSV; snapshotถูกบันทึกหลังการอ่าน/เขียน ไม่เท่ากับเวลาป้อนinputหรือphysical onset
- มอเตอร์ใช้raw encoder ticks; 4096ticksต่อ360° Commanded Positionมาจากcommand_goalsซึ่งเป็นcacheเป้าที่ส่ง ส่วนActual Encoderมาจากposition_raw เพิ่มgoal registerreadbackและเวลาfeedback CLOCK_MONOTONICไว้ต่างหาก ไม่แปลงclockนี้เป็นBOOTTIMEโดยเดา ไม่อ้างว่าcommandกับencoderอ่านพร้อมกัน
- กราฟ4: CPG logical output time = updates × dt / time_scale; dt=.05s,time_scale=.5 ไม่ใช่เวลาที่วัดการเคลื่อนมอเตอร์

## วิธีคำนวณ metric

`CSV/05_metrics.csv` คือค่าที่คำนวณได้พร้อมสูตร/หน่วย ทั้งคู่มี7คาบสมบูรณ์และ6คู่คาบ

1. Max Δφ = max |φ[i]−φ[i−1]| ระหว่างsnapshotติดกัน อัตราcallbackไม่คงที่ จึงไม่ใช่การเปลี่ยนต่อ50msตายตัว
2. Deduplicate o1 ที่updatesซ้ำ แล้วหาจุดข้ามศูนย์ขึ้นด้วยlinear interpolationระหว่างจุดที่บันทึกจริง
3. T = t_cross[n+1]−t_cross[n]; timestampของคาบในCSVคือจุดจบคาบ
4. ΔT = |T[n]−T[n−1]|; คาบแรกไม่มีค่าก่อนหน้า จึงเว้นช่องว่าง ไม่แทน0
5. Mean Frequencyหลัก = 1/mean(T) และส่งmean(1/T)อีกแถวโดยติดชื่อแยก ไม่ใช้แทนกัน

การinterpolateใช้เฉพาะประมาณเวลาข้ามศูนย์สำหรับmetric ไม่สร้างหรือเติมCPG waveform nodes ขาดไป15nodesในC0/10ในC1 บอกจำนวนไว้ครบ ช่วงencoderpeak-to-peakในmetricsตัดelapsed<5sตามรายงานต้นทาง แต่CSVและกราฟส่งครบทุกแถว

## ข้อสรุปสำหรับสไลด์

- C1 has smaller observed phi steps than C0.
- CPG mean Delta T is 0.428482 s (C0) versus 0.460994 s (C1); it does not decrease in this pilot.
- Physical motor smoothness was not established.

ห้ามเขียนว่าC1ทำให้มอเตอร์สมูทขึ้น91.5% ตัวเลขที่เคยรายงานเป็นการลดmax parameter-stepเท่านั้น ไม่ใช่ความสมูททางกล

## ข้อจำกัด

มีเพียงหนึ่งคู่50s; ไม่ใช่3repeatsหรือการเล่นกับคน10นาที ค่าเริ่มCPGเหมือนกันแต่encoderเริ่มจริงต่างกัน ทั้งสองข้าม359parameter indicesอ้างอิงระหว่างowner callbacks แม้fixtureมีครบ1000samples จังหวะใช้พารามิเตอร์จริงจึงไม่ตรงกันทุกครั้ง

มีencoderquantizationและcommand/feedbackเวลาต่างกัน ยังไม่ได้วัดmotorfrequency/jerk/physical onset การเห็นoffsetหรือencoderขยับน้อยกว่าเป้าแยกสาเหตุfriction/backlash/load/PIDไม่ได้ ไม่สรุปนัยสำคัญทางสถิติหรือการทำงานทั้ง6อารมณ์จากคู่นี้

## หลักฐานตรวจย้อนกลับ

`raw_sources/c0_r01` และ`c1_r01` เก็บJSONต้นฉบับพร้อมmanifest/verification; `raw_sources/comparison_r01` เก็บรายงาน/metricsเดิม; `raw_sources/deployment` เก็บprofile/sourceตามSHAของpilot (camera_motor.pyดึงจากpayloadเก่า ไม่ใช้ไฟล์ปัจจุบันที่เปลี่ยนรุ่นแล้ว). ทั้งสองprofileต่างกันเฉพาะnormal_ahm_condition

`SOURCE_AUDIT.json` ระบุไฟล์และSHA; `MANIFEST_SHA256.json` ตรวจทุกไฟล์ในชุด ค่าmetricคำนวณซ้ำจากrawและตรงกับmetricsเดิม ไม่มีการแก้ต้นฉบับ
