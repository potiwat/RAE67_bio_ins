# ข้อเสนอการทดลอง: ความทนทานของโคมไฟ AHM–SO(2) CPG ต่อ combined jitter/drop

ผู้จัดทำ: ภาณุพร มาศรี (6752500118)
สถานะเอกสาร: ข้อเสนอสำหรับงานในอนาคต ยังไม่ได้รัน ROS 2, หุ่นยนต์จริง หรือการทดลองกับคน

## 1. คำถามและสมมติฐาน

คำถามหลักคือ เมื่อใช้ stimulus sequence เดียวกันใน human–lamp scenario 600 s transport profile ที่รวม delay jitter และ message drop จะทำให้ความถี่การพยักหน้า, source-to-physical motion/RGB latency และสัดส่วน response ที่หายต่างจาก ideal transport หรือไม่ ภายใต้ controller ที่ใช้ artificial hormone mechanism (AHM) ปรับ SO(2) CPG

สมมติฐานที่ประกาศล่วงหน้าคือ C1 จะมี median `both_latency_s` และ `response_missing_fraction` สูงกว่า C0 และมีความแปรปรวนของ `nod_frequency_hz` ภายใน trial สูงขึ้น การทดลองนี้เปลี่ยน jitter กับ drop พร้อมกัน จึงตีความได้เฉพาะผลของ combined profile ไม่สามารถบอก causal effect ของ jitter หรือ drop แยกกันได้ หากต้องการแยกผลต้องเพิ่ม delay-only และ drop-only conditions ใน protocol ใหม่

## 2. Biological inspiration และสมการ

แนวคิด AHM อ้างอิงการสะสมและการปล่อย artificial hormone จาก Homchanthanakul et al. (2019), DOI `10.1109/IROS40897.2019.8968580` และ architecture การปรับพฤติกรรมจาก Ngamkajornwiwat et al. (2020), DOI `10.1109/ACCESS.2020.2992794` การนำมาใช้กับโคมเป็น engineering analogy ของ arousal ที่รวม stimulus ตามเวลา ไม่ใช่การอ้างว่าจำลองระบบต่อมไร้ท่อของคน

สมการอ้างอิงเขียนได้เป็น

```text
H_c(t) = beta H_c(t-1) + H_g(t) - H_r(t)
H_g(t) = alpha_h f(S(t))
H_r(t) = sum_i gamma_i Receptor_i(t)
```

แบบจำลองที่วางแผน implement ใช้ Euler form จาก Lab 04 เพื่อให้หน่วยและลำดับ update ชัดเจน

```text
P = k_prod S
C = k_clear H_old
B = k_bind R_old
H_new = clamp(H_old + dt_h(P-C-B), 0, 1)
R_new = clamp(H_new, 0, 1)
```

SO(2) CPG ใช้ simultaneous update จาก Week 03

```text
a1(t+1) = alpha_cpg[cos(phi)o1(t) + sin(phi)o2(t)]
a2(t+1) = alpha_cpg[-sin(phi)o1(t) + cos(phi)o2(t)]
o1(t+1) = tanh(a1(t+1))
o2(t+1) = tanh(a2(t+1))
```

AHM เชื่อมกับ CPG ผ่าน `phi=clamp(phi_0+phi_gain*R, phi_min, phi_max)` แล้วสร้าง `nod_cmd=clamp(nod_gain*o1,-nod_limit,nod_limit)`. FSM จาก Lab 06–07 ยังคง priority `fault > near > clear` และเลือก RGB/state expression เพื่อไม่ให้ CPG ข้าม safety guard

## 3. ระบบและ boundary ที่วัด

```text
button/touch/distance + UUID + acquisition time
             │
             ▼
transport profile → receipt → guards/FSM → AHM → SO(2) CPG
                                               │
                         ┌─────────────────────┴──────────────────┐
                         ▼                                        ▼
                 nod command [rad]                         RGB command [0..1]
                         │                                        │
                    servo/driver                              RGB driver
                         │                                        │
                 camera/encoder onset                    photodiode onset
```

`Bool`, `Float32`, `String` และ `ColorRGBA` ใน interface เดิมไม่มี Header จึงต้องเพิ่ม versioned stamped wrapper/sidecar ที่ส่ง UUID และ source time โดยไม่เดา identity จาก payload ซ้ำกัน ทุก node บันทึก local monotonic time ส่วน ESP32 บันทึก MCU tick. ก่อนและหลัง trial ใช้ two-way synchronization pulse เพื่อประมาณ offset/drift และส่ง common TTL marker ไปยัง acquisition logger, motion recorder และ photodiode DAQ. Error bound นิยามเป็น maximum synchronization residual บวกครึ่ง sampling period ที่ช้าที่สุด ถ้าเกิน 0.005 s ให้ physical latency เป็น N/A

CPG เคลื่อนไหวต่อเนื่องได้ จึงไม่สามารถถือ motion ที่กำลังเกิดอยู่เป็น onset ของ event ใหม่ การวัด latency จะใช้เฉพาะ gated rest-to-motion probes ที่ประกาศ UUID ไว้ก่อนทดลอง: คง nod ที่ 0 rad และ RGB neutral 1.0 s, initialize oscillator ที่ `(o1,o2)=(0.1,0)`, warmup CPG ภายใน 1.0 s โดยยังปิด physical gate แล้วเปิด gate เมื่อ event มาถึง เหตุการณ์อื่นระหว่าง ongoing motion เก็บใน all-source log แต่ไม่ถูกนำมาเป็น onset ใหม่

## 4. Experimental design

Independent variable มีหนึ่งปัจจัยคือ transport profile สองระดับ

| Condition | Transport | Repeats |
|---|---|---:|
| C0 ideal | delay=0, drop=0, ไม่มี burst | 12 |
| C1 combined | delay จาก 0/.02/.04/.06/.10/.14/.18 s, random drop=.08, burst 312.50–312.70 s | 12 |

Simulation ใช้ 12 fixed seeds แบบ paired ระหว่าง C0/C1 งาน real robot ที่วางแผนใช้ผู้เข้าร่วม 12 คนแบบ paired crossover: participant ID คี่ทำ C0→C1 และ ID คู่ทำ C1→C0 มี reset และพักอย่างน้อย 5 นาทีระหว่าง conditions. แต่ละคนใช้ UUID stimulus script เดียวกันทั้งคู่ เก็บ conflict/fault probes และ outcome ที่ไม่มี onset ไว้ ไม่คัดเฉพาะ success

ตัวแปรควบคุมประกอบด้วย policy/code commit, AHM/CPG parameters, initial state, bounds/slew, lamp/servo/firmware, sensor placement, power supply, QoS, calibration files, room light, camera/photodiode และ logging rate. ก่อนทุก trial reset H, CPG, FSM, queue และ log origin แล้วใช้ neutral/warmup procedure เดียวกัน

ค่าหลักที่ตั้งล่วงหน้า ได้แก่ `dt_h=.05 s`, `k_prod=.8`, `k_clear=.6 s^-1`, `k_bind=.2`, `alpha_cpg=1.1`, `dt_cpg=.05 s`, `phi_0=.20 rad/update`, `phi_gain=.20`, bounds `[.10,.45]`, nod gain/limit `.30 rad`. ค่าเหล่านี้เป็น proposed course model และต้องสอบเทียบก่อนใช้กับ actuator จริง

## 5. Metrics, attribution และ missing rules

1. `nod_frequency_hz`: inverse mean period ของ rising zero crossings ของ measured nod angle ใน analysis block 60 s ใช้ crossing ที่ endpoints valid และอยู่ใน block ทั้งคู่ ถ้ามี rising crossings น้อยกว่าสองครั้ง, tracking หาย หรือ safety stop ทำให้ block ใช้ไม่ได้ ให้ค่า N/A พร้อมเหตุผล
2. `both_latency_s`: สำหรับ gated probe เท่านั้น เป็น `max(nod onset, RGB onset)-UUID acquisition time`. Nod onset คือ measured angle ออกจาก neutral อย่างน้อย .01 rad ต่อเนื่อง 3 camera frames; RGB onset คือ photodiode เปลี่ยนอย่างน้อย .05 normalized units ต่อเนื่อง 3 samples; observation window 1.0 s
3. `response_missing_fraction`: จำนวน expected gated UUID ที่ไม่มี motion+RGB onset ครบภายใน 1.0 s หาร frozen activation-probe denominator

Outcome ของทุก source ใช้ status ที่ไม่ทับกัน: `responded`, `missing`, `overlap`, `held`, `censored`, `invalid_clock`. Event ซ้อนก่อน attribution window ปิดเป็น overlap, policy ตั้งใจคง state เป็น held, trial end/safety stop เป็น censored และ identity/clock error เกินเกณฑ์เป็น invalid_clock. เฉพาะ responded จึงมี latency ตัวเลข ค่าอื่นเป็น null พร้อม status ไม่แทนด้วย 0 และไม่ใช้ ongoing CPG motion เป็น onset

Primary gated IDs จะ freeze ใน manifest ก่อนรันเป็น `button_activate_b01` ถึง `b05` และ `touch_activate_b01` ถึง `b05` ส่วน approach/clear/near, conflict, fault และ ongoing-motion events ยังคงอยู่ใน all-source table การ freeze denominator ป้องกันการเลือก subset หลังเห็นผล

## 6. แผน simulation และ real robot

ขั้น simulation จะเพิ่ม AHM และ SO(2) nodes ใน timestamped simulator รัน 600 s ต่อ condition × 12 paired seeds และเก็บ source, receipt, decision, H/R, oscillator, gate, applied command และ synthetic physical onset พร้อม config/source snapshot/SHA-256 manifest. Analysis code และ denominator จะ freeze ก่อนเปิด condition labels. ผล offline 22 s ที่ทำใน Lab 07 ปัจจุบันเป็นเพียง protocol/replay check ไม่มี AHM/CPG และไม่นับเป็นผล simulation นี้

ขั้น real robot จะทำหลัง simulation, safety review และ ethics approval เท่านั้น เป้าหมายคือ Ubuntu 24.04/ROS 2 Jazzy, micro-ROS ESP32, calibrated button/touch/distance sensors, nod servo และ RGB. เริ่มจาก bench calibration แบบไม่มีผู้เข้าร่วมเพื่อหา rad-to-PWM mapping, joint limits, camera angle noise floor และ photodiode noise floor แล้วจึงยืนยัน threshold .01 rad/.05 normalized อยู่เหนือ noise จริง หากไม่ผ่านต้องแก้ protocol และ preregister ค่าใหม่ก่อน trial

แต่ละ participant เล่นกับโคม 600 s ต่อ condition. เก็บ rosbag, MCU sidecar, camera/encoder, photodiode, calibration และ environment log โดยไม่ใช้ command receipt แทน physical onset. ขอ written informed consent, ใช้ pseudonymous ID, อนุญาตให้ถอนตัวโดยไม่มีผลเสีย และแยก linkage file ออกจาก de-identified traces

## 7. Safety และแผนวิเคราะห์

ผู้ควบคุมถือ hardware power-cut emergency stop ตลอดเวลา หยุดทันทีเมื่อโคมสัมผัสผู้เข้าร่วม, เคลื่อนไหวผิดคาด, command เกิน calibrated limit, stale/fault ต่อเนื่องเกิน .5 s, current/temperature เกินผู้ผลิตกำหนด, hardware หลวม, clock/logger ล้มเหลว หรือผู้เข้าร่วมขอหยุด เมื่อหยุดให้ตัด servo power, ตั้ง RGB neutral, เก็บ log, label trial เป็น censored และตรวจสาเหตุก่อนเริ่มใหม่

การวิเคราะห์หลักใช้ paired C0–C1 difference ต่อ seed/participant รายงาน median/IQR ของ latency, missing/status counts และ block-level frequency พร้อม raw points ไม่สรุปจาก successful responses อย่างเดียว ผลที่คาดคือ C1 ช้าหรือมี missing มากขึ้น แต่ถ้าบาง repeat ไม่ต่างต้องรายงานเป็น null/negative result. เนื่องจาก C1 เป็น composite factor จึงไม่กล่าวว่า reliable DDS หรือ hardware จริงมีพฤติกรรมเหมือน model นี้

## 8. Timeline ที่วางแผน

- 16–22 พ.ย. 2026: implement และ unit-test timestamped AHM–CPG simulation รวม gated probes
- 23–29 พ.ย. 2026: รัน paired simulation, ตรวจ manifest และ freeze analysis
- 30 พ.ย.–6 ธ.ค. 2026: bench calibration และ safety review
- หลังได้รับ ethics/consent approval: รัน 12 paired participant trials
- สองสัปดาห์หลัง trials: วิเคราะห์ de-identified data, ตรวจ uncertainty และเขียนข้อจำกัด

ข้อเสนอนี้ระบุสิ่งที่จะทำและเกณฑ์ที่ใช้ตัดสินล่วงหน้า ไม่ได้อ้างว่าขั้น ROS, hardware หรือ human study เกิดขึ้นแล้ว และการผ่าน `check_proposal.py` ยืนยันเพียงความครบของ field ไม่ใช่การรับรอง scientific validity หรือ ethics approval
