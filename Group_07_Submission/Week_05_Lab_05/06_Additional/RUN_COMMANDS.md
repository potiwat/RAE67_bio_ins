# คำสั่งรันซ้ำ Lab05

รันจากโฟลเดอร์ Week_05_Lab_05 ใช้ Python 3.10 ขึ้นไป ไม่ต้องติดตั้ง package เพิ่ม
Python ที่ใช้ทำงานเดิม: 3.13.7
ผลต้นฉบับอยู่ใน 03_Results คำสั่งนี้สร้างผลใหม่ใน results_reproduced
เลือก output directory ใหม่หากเคยรันคำสั่งนี้แล้ว

```powershell
py -3 --version
py -3 02_Source/lab05.py --condition all --profile step --mapping both --output-dir results_reproduced/comparison
py -3 02_Source/lab05.py --condition all --profile step --mapping phi-only --output-dir results_reproduced/phi_only
py -3 02_Source/lab05.py --condition all --profile fault --mapping both --output-dir results_reproduced/fault_02
py -3 02_Source/contact_demo.py --output-dir results_reproduced/contact
```

Linux/macOS ใช้ python3 แทน py -3
เปิด report.html ภายในแต่ละโฟลเดอร์ผลด้วย browser
Mapping phi-only เป็นตัวเลือกที่กลุ่มเลือกจากโจทย์ที่ให้เลือก phi-only หรือ stride-only
ชื่อ fault_02 คือชื่อโฟลเดอร์ผลที่กลุ่มใช้
คู่มืออาจารย์ฉบับเดิมอยู่ใน README_Original.md โดย path ของโค้ดในคู่มือนั้นอ้างโครงสร้างต้นฉบับ
