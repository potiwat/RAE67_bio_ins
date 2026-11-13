# Lab 7 · ซอร์สและวิธีคำนวณผลจากหุ่นจริง

โคม LampBio-Inpire ใช้ตัวเปิด `present` บันทึกข้อมูลวันที่ 12 พฤศจิกายน 2026 จำนวน 3 คู่ คู่ละ C0 และ C1 เงื่อนไขละ 180 วินาที C0 ส่งสิ่งเร้าโดยตรงเป็น (R=S) ส่วน C1 ใช้ค่าฮอร์โมน (R=H) สัญญาณปุ่ม สัมผัส และ Near ในช่วงวัดมาจากตารางสิ่งเร้าของงานวิจัย กล้องและเอ็นโคเดอร์ทำงานบนหุ่นจริง คู่ที่ 1 ใช้คนเป็นเป้ากล้อง คู่ที่ 2 และ 3 ใช้ภาพบุคคลบนจอ ลำดับทดลองเป็น C0 → C1, C1 → C0 และ C0 → C1 ตามลำดับ

## คำนวณซ้ำบนพีซี

เปิดเทอร์มินัลที่โฟลเดอร์หลักของชุดส่ง ซึ่งมี `02_Source` และ `03_Results` อยู่ข้างกัน เมื่อมี Python, NumPy และ Matplotlib แล้ว ใช้คำสั่งนี้เพื่อตรวจและคำนวณซ้ำทั้งหมด

```sh
python -B 02_Source/reproduce.py
```

คำสั่งอ่านไฟล์ใน `03_Results/real_robot/P1…P3/C0,C1/original` แล้วสร้างตารางและกราฟในพื้นที่ชั่วคราว เมื่อต้องการเก็บผล ให้ตั้งชื่อโฟลเดอร์ใหม่

```sh
python -B 02_Source/reproduce.py --output ../Lab07_rebuilt
```

บน Windows ที่ใช้ Python 3.13 ติดตั้งรุ่นที่ตรวจแล้วได้ด้วย `py -3.13 -m pip install -r 02_Source/requirements.txt` และเรียกโปรแกรมด้วย `py -3.13 -B 02_Source/reproduce.py` การคำนวณใช้ไฟล์ในชุดส่งบนพีซีได้โดยปิดหุ่นไว้

| สิ่งที่จะตรวจ | ตำแหน่งผล |
|---|---|
| เวลาและ SHA-256 ประจำรอบ จำนวนตัวอย่าง และเป้ากล้อง | `real_robot/summary/Run_index.csv` |
| สิ่งเร้า H, R, φ, สัญญาณทุก CPG และ encoder ห้าแกน | `real_robot/P*/C*/control.csv`, `all_CPG_banks.csv` และ `five_joint_feedback.csv` |
| การเปลี่ยนสถานะและเวลาตอบสนองต่อขอบสัญญาณ | `real_robot/P*/FSM_events.csv`, `response_edges.csv` และ `run_quality.csv` |
| คาบ CPG เต็มรอบและ M1/M2 แยกตามคู่ เงื่อนไข และสถานะ | `real_robot/summary/CPG_cycles.csv` และ `Worksheet_M1_M2.csv` |
| ค่า H กับ φ ช่วงปล่อยสัมผัส คาบส่ายจริงของ ID1 และช่วง ON/OFF | `real_robot/summary/Happy_H_phi_samples.csv`, `Happy_dance_cycles.csv` และ `Happy_ON_OFF_periods.csv` |
| กราฟที่ใช้ในรายงาน | `Figures/01_Happy_input_CPG_and_encoder.png`, `02_Touch_release_all_pairs.png` และ `03_Six_state_timeline.png` |

โปรแกรมตรวจ SHA-256 ของไฟล์ต้นฉบับ 111 ไฟล์ ตรวจนาฬิกาและกฎคัดช่วงก่อนวิเคราะห์ แล้วคำนวณจากข้อมูลดิบ 21,464 แถว มีค่า φ ที่ใช้วิเคราะห์ได้ 21,458 แถวในช่วง `0 ≤ t < 180 s` ตารางรายคู่ผ่านการปัดตามความละเอียดของ export ต้นทางก่อนคำนวณสรุป ชุดผลที่ส่งใช้เป็นค่าเปรียบเทียบหลังคำนวณ

บน Ubuntu 24.04 ผ่าน WSL (Python 3.12.3, NumPy 1.26.4, Matplotlib 3.6.3, FreeType 2.13.2) ไฟล์ CSV ทั้ง 33 และ PNG ทั้ง 3 ตรงกันทุกไบต์ สามารถบังคับตรวจไบต์ของ PNG ด้วย `--strict-figures` บน Windows (Python 3.13.7, NumPy 2.3.3, Matplotlib 3.10.7) CSV ตรงกันทุกไบต์ 31 ไฟล์ อีก 2 ไฟล์ต่างเฉพาะ `mean_H` จากการปัดทศนิยมของผลคูณเชิงตัวเลข ต่างสูงสุด 7.8 × 10⁻¹⁶ ตาราง M1/M2 ตรงกันทุกไบต์ PNG จาก Matplotlib ต่างรุ่นมีรายละเอียดการเรนเดอร์และข้อมูลกำกับต่างกัน

## ซอร์สของตัววิเคราะห์

`analysis/review_pair.py` แปลงนาฬิกาของ snapshot และของเซอร์โวให้เทียบกันได้ ตรวจความสัมพันธ์ S/H → R → φ และส่งออกข้อมูลห้าแกน `analysis/window_quality.py` ตรวจคุณสมบัติของช่วงวัดจากไฟล์ดิบ รวมถึงเวลาสลับอินพุตหลังสิ้นสุด P1

`analysis/hormone_response.py` หาคาบจากจุดตัดศูนย์ขาขึ้นของ (o_1) ที่แทรกเวลาเชิงเส้น ใช้นาฬิกาเอาต์พุตของแต่ละ CPG เก็บเฉพาะช่วง FSM/ท่าจริงตรงกัน เอาต์พุตเต็ม และข้อมูลต่อเนื่อง M1 คือ 1 / ค่าเฉลี่ยคาบ หน่วย Hz และ M2 คือค่าเฉลี่ยผลต่างสัมบูรณ์ระหว่างคาบติดกันในช่วงต่อเนื่องเดียวกัน หน่วยวินาที ค่า `N/A` หมายถึงจำนวนคาบในช่วงนั้นไม่พอ `analysis/transition_review.py` วัดคาบส่ายจากการผ่านมุมกึ่งกลางของ encoder ID1 ในทิศเดิมโดยยืนยันทั้งด้านต่ำและสูง โค้ดวาดกราฟอยู่ใน `analysis/hormone_response_figures.py`

## ซอร์สที่ผูกกับการเก็บข้อมูล

ในเอกสารชุดนี้โคมใช้ชื่อ LampBio-Inpire และเรียกตัวเปิดว่า `present` สำเนาซอร์สใน `hardware/` คงชื่อไฟล์ เส้นทาง และข้อความตามที่บันทึกบน Pi เพื่อให้ตรวจ SHA-256 และรันการวิเคราะห์ย้อนหลังได้ ตัวเปิดบน Desktop ทั้งสองไฟล์อยู่ใต้ `hardware/home/menulis/Desktop/`

| ตำแหน่งใต้ `hardware/` | หน้าที่ |
|---|---|
| [instrument.py](hardware/bio_inspire/experiments/lab07_present_safety_pair1_20261112/instrument.py) | ตัวบันทึก 180 วินาที ตารางป้อนสิ่งเร้า และการเลือก C0/C1 ค่า SHA-256 ตรงกับ `study_sha256` ของทั้งหกรอบ |
| [portrait_study.py](hardware/bio_inspire/experiments/lab07_present_safety_pair1_20261112/portrait_study.py) | ตัวปรับเงื่อนไขเริ่มเมื่อกล้องเห็นใบหน้าบนจอสำหรับ P2/P3 ค่า SHA-256 ตรงกับ `portrait_sha256` ของทั้งสี่รอบ |
| [ชุดซอร์สของตัวเปิด present](hardware/shared/experiments/presentation_safety_play_20261110/) | [สคริปต์เริ่มโปรแกรม](hardware/shared/experiments/presentation_safety_play_20261110/present_safety_start.py), `launch.py`, โปรไฟล์ `profile.json`, ค่าตรวจ `config.json` และรายการ SHA-256 ต้นฉบับ `manifest.json` |
| `bio_inspire/runtime/`, `shared/runtime/` | FSM, AHM, CPG, การแปลงเป็นเป้าข้อต่อ, เซนเซอร์ และตัวควบคุมของโคม |
| `supplemental_sources.json` | SHA-256 และที่มาของตัวกำหนดจังหวะ Happy, ฟังก์ชันตรวจตัวอย่าง ToF ตอนเริ่ม, โมดูล telemetry, ตัวอ่านบัส และไฟล์ภาพเป้ากล้อง |

ไฟล์ใต้ `hardware/` ที่มีชื่อ `trial`, `test_` หรือ `last_` บางรายการเป็นไฟล์ที่ตัวเปิดกำหนดให้ตรวจแฮชก่อนทำงาน ชื่อและเนื้อหาจึงคงตามฉบับที่บันทึกไว้ ตารางและกราฟ Lab 7 อ้างอิงเฉพาะหกรอบใน `03_Results/real_robot`

[ภาพอ้างอิงที่ใช้เป็นเป้ากล้อง](hardware/bio_inspire/experiments/lab07_present_safety_pair1_20261112/qa/face_target_grace_hopper.jpg) มี SHA-256 `a8ca6d734765703b09728ab47fe59f473d93ae3967fc24c7c0288c3c7adb7130` ตรงกับตัวอย่าง `grace_hopper.jpg` ของ Matplotlib หลักฐานจาก P2/P3 บันทึกการตรวจพบใบหน้าผ่านกล้อง ส่วน `portrait_sha256` ในไฟล์ประจำรอบเป็นแฮชของโปรแกรมปรับการเริ่มวัด [ภาพตัวอย่างจาก Matplotlib](https://matplotlib.org/3.6.3/gallery/images_contours_and_fields/image_demo.html)

**ข้อจำกัดของสำเนาฮาร์ดแวร์** ตัวเปิดบน Pi ตรวจไฟล์ 240 รายการก่อนรัน ทั้งหกรอบมีหลักฐานแฮชของ manifest เดียวกัน ในชุดนี้ตรวจต้นฉบับตรงได้ 237 รายการ (ของตัวเปิด 94/95, ไฟล์ที่ระบบป้องกัน 130/132, dependency 13/13) โปรแกรมทดสอบ `test_release_plan.py` กับไฟล์วินิจฉัยเดิม `last_camera_frame.json` และ `last_gaze_stop.json` ยังไม่มีสำเนาที่ตรงแฮช รายการเส้นทางและแฮชที่ต้องใช้ครบอยู่ใน `hardware/manifest_coverage.json` การติดตั้งบน Pi เครื่องใหม่ต้องมีต้นฉบับสามไฟล์นั้นจึงจะผ่านการตรวจของตัวเปิด โปรแกรมตรวจผลบนพีซีใช้ข้อมูลและซอร์สที่รวมไว้ครบทั้งหกรอบ
