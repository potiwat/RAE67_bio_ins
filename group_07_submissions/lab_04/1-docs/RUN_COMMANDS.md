# คำสั่งรันซ้ำ

รันจากโฟลเดอร์ Week_04_Lab_04 ใช้ output-dir ที่ยังไม่มีผลรัน

```powershell
New-Item -ItemType Directory -Force 03_Results/Grader | Out-Null
py -3 02_Source/check_submission.py --student-file 02_Source/student_hormone.py 2>&1 | Tee-Object -FilePath 03_Results/Grader/checker_output.txt
py -3 02_Source/lab04.py --controller-source student --condition all --profile step --output-dir results_reproduced/comparison
py -3 02_Source/lab04.py --controller-source student --condition C1 --profile zero --output-dir results_reproduced/zero
py -3 02_Source/lab04.py --controller-source student --condition C1 --profile one --output-dir results_reproduced/one
py -3 02_Source/lab04.py --controller-source student --condition C1 --profile spike --output-dir results_reproduced/spike
py -3 02_Source/lab04.py --controller-source student --condition C1 --profile fault --output-dir results_reproduced/fault
```

config/hash อยู่ใน 03_Results ของแต่ละชุดการทดลอง

คำสั่งทดสอบ contract เดิม Week03

```powershell
py -3 02_Source/lab04.py --controller-source student --condition C1 --profile step --contract 02_Source/week03_handoff_contract.json --output-dir results_reproduced/Week03_Handoff
```
