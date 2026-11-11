# Lab 04 — Worksheet answers

## A. Prediction และเหตุผล

| Comparison | prediction ก่อนรัน | เหตุผลจาก term ในสมการ | ผลจริงหลังรัน |
|---|---|---|---|
| C2 vs C1 | C2 สะสม H เร็วและมี AUC สูงกว่า | `k_prod` เพิ่มจาก .8 เป็น 1.2; peak อาจถูกจำกัดที่ 1 | rise 1.05 s เทียบ 2.70 s; AUC 10.672410 เทียบ 9.999644 H·s; peak ทั้งคู่ ≈1 |
| C3 vs C1 | C3 ลด H ช้ากว่า | `k_clear` ลดจาก .6 เป็น .25 | recovery 5.10 เทียบ 2.85 s; AUC 11.389145 เทียบ 9.999644 |
| C4 vs C1 | H/AUC สูงขึ้นและฟื้นช้าลง | `k_bind=0` จึงตัด binding removal | AUC 10.754721 เทียบ 9.999644; recovery 3.80 เทียบ 2.85 s |
| C0 vs C1 | C0 ไม่มี hormone state | C0 ใช้ direct R=S ไม่ integrate H | H/AUC ของ C0 เป็น N/A/null |

Prediction ที่อาจเปลี่ยนจาก upper bound=1: C2/C3/C4 อาจมี peak เท่ากับ C1 แม้ production หรือ removal ต่างกัน จึงใช้ AUC, recovery และ clamp fraction ร่วมกัน.

## B. ตรวจสมการและคำนวณมือ

Source equation ที่อ้างในเอกสารเป็นสมการสร้าง/สลายฮอร์โมนตาม receptor; Lab นี้ใช้ **proposed course model** แบบ Euler: `R_old=clamp((H_old−H_min)/(H_max−H_min),0,1)`, `P=k_prod S`, `C=k_clear H_old`, `B=k_bind R_old`, `H_raw=H_old+dt(P−C−B)`, จากนั้น clamp H และคำนวณ R ใหม่. สองสมการนี้มี provenance ต่างกัน ไม่ใช่การอ้างว่ารัน paper model.

ทดสอบ receptor: H=.2, H_min=.1, H_max=.5 → `(.2−.1)/(.5−.1)=.25`.

| input_time_s | time_s | P | C | B | H_raw | H | R | φ (rad) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10.00 | 10.05 | .800 | .000 | .000 | .0400 | .0400 | .0400 | .20800 |
| 10.05 | 10.10 | .800 | .024 | .008 | .0784 | .0784 | .0784 | .21568 |

stride half ในสองแถวเท่ากับ .0554 m และ .055784 m ตามลำดับ. CSV ใช้ `input_time_s` เป็นต้นช่วง stimulus; `time_s` คือเวลาหลัง update หนึ่ง `dt=.05 s`.

## C. Controlled comparison

| Condition | peak_H | AUC_H | latency (s) | rise (s) | recovery (s) | upper clamp fraction | φ TV (rad) |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 | N/A | N/A | .050 | .000 | .050 | N/A | .400000 |
| C1 | .999715 | 9.999644 | .150 | 2.700 | 2.850 | .000000 | .399829 |
| C2 | 1.000000 | 10.672410 | .100 | 1.050 | 2.850 | .290000 | .399943 |
| C3 | 1.000000 | 11.389145 | .150 | 1.450 | 5.100 | .273333 | .397890 |
| C4 | 1.000000 | 10.754721 | .150 | 1.700 | 3.800 | .258333 | .399548 |

C3 ฟื้นช้ากว่า C1 2.25 s. C2/C3 peak เท่ากันที่ 1.0; AUC และ recovery แยกผลได้. C0 ไม่มี H; fields เป็น null/N/A. ค่า TV ของ φ ไม่พิสูจน์คุณภาพ gait เพราะไม่ได้จำลองหรือวัด gait ใน Lab04.

## D. Extreme tests และ handoff

- zero: peak H=0, φ/stride TV=0.
- one: peak H≈1.
- spike: S=1 หนึ่ง sample ที่ input 10.00 s; peak H=.04.
- fault: input 15.00 s มี fault flag และ reset H/R/raw/P/C/B เป็น 0; valid input 15.05 s ทำให้ state 15.10 s กลับมา H=R=.04.
- mapping: R=0 → φ=.20 rad, stride half=.055 m; R=1 → φ=.40 rad, stride half=.065 m.
- สิ่งที่ยังไม่ได้ทดสอบ: CPG/body gait integration, actuator limits, emergency stop, hardware response และ dynamic stability.

## E. สรุป

1. Stimulus ปรับ P; H เปลี่ยนจากผลรวม P−C−B ตาม Euler course model; receptor อ่าน H ใหม่และ bounded mapping ส่ง φ/stride ต่อไป. Checker ผ่าน 13/13.
2. ผลสนับสนุนว่า C3 ฟื้นช้ากว่า C1 2.25 s; C2 และ C3 มี peak เท่ากันเพราะ upper clamp แต่ AUC ต่างกัน.
3. ข้อจำกัดคือเป็น deterministic proposed course model; ต้องเชื่อมและทดสอบ gait ใน Lab05 ก่อนสรุปผลต่อการเดิน และต้องตรวจ safety/limits แยกก่อนใช้งาน hardware.

ผล CSV, metrics, config, plots และ HTML อยู่ใน `results/lab04_complete_20261111/`.
