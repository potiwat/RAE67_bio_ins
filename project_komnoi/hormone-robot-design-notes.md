# หลักการออกแบบหุ่นยนต์ที่ใช้ฮอร์โมนเทียม (Design Notes)

สรุปหลักการจากการเตรียมสอบวิชา Bio-Inspired Robotics (1353410 / RAE67) จากเคสหุ่น AMPHI-DRACO, HEXA-RESCUE และ TERRA-LUX เพื่อเอาไปใช้ออกแบบหุ่นยนต์ตัวใหม่ที่ใช้ Artificial Hormone Mechanism (AHM)

**วิธีใช้ไฟล์นี้**

- แนบไฟล์นี้ตอนเริ่มแชทใหม่ หรือวางไว้ในโฟลเดอร์โปรเจกต์ แล้วบอก Claude เช่น "อ่าน design notes นี้ก่อน แล้วช่วยออกแบบและเขียนโค้ดหุ่นตัวใหม่ตามหลักการนี้ เริ่มจากหัวข้อ 0"
- กรอกหัวข้อ 0 (สเปกหุ่น) ก่อน ยิ่งกรอกครบ ยิ่งออกแบบได้ตรง
- ตัวเลขทุกตัวในไฟล์เป็นค่าตั้งต้นตัวอย่าง ต้องจูนกับหุ่นจริง
- โค้ดเป็น Python แบบ reference เน้นอ่านง่าย รันผ่านการทดสอบเบื้องต้นแล้ว แต่ยังไม่ใช่โค้ด real-time สำหรับบอร์ดจริง

---

## 0. สเปกหุ่นตัวใหม่ (กรอกก่อนเริ่ม)

| หัวข้อ | กรอก |
|---|---|
| ชื่อหุ่น | |
| รูปร่าง (กี่ขา, ข้อต่อต่อขา, ลำตัวมีข้อต่อไหม) | |
| ภารกิจและสภาพแวดล้อม | |
| เซนเซอร์ภายนอก (exteroceptive) | |
| เซนเซอร์ภายใน (proprioceptive) | |
| actuator และ driver | |
| บอร์ด fast loop / บอร์ด slow loop | |
| ฮอร์โมนที่อยากมี (เช่น caution, fatigue, curiosity) และสิ่งเร้าของแต่ละตัว | |
| ช่องทางสื่อสาร (ไฟ, เสียง, จอ) | |
| โหมดปลอดภัยพื้นฐานของภารกิจนี้ (safe default) | |

---

## 1. ภาพรวมสถาปัตยกรรม

```
[เซนเซอร์] Exteroceptive + Proprioceptive (encoder, force/tactile, IMU, กระแสมอเตอร์)
   |
   v
FAST LOOP (~100 Hz, บอร์ด real-time ใกล้มอเตอร์, ไม่รอ slow loop)
   validate (NaN / range / timeout / stale) -> low-pass filter -> hysteresis / debounce
   -> reflex (phase resetting, elevator reflex)
   -> closed-loop CPG + decoder
   -> Actuator Safety Interface (clamp, slew-rate, torque limit) -> มอเตอร์
   watchdog เฝ้าทุกโมดูล + E-stop แบบฮาร์ดแวร์
   |  ^
   |  |  พารามิเตอร์ (ความถี่, amplitude, โหมด) ผ่าน Bounded Modulation Interface
   v  |  (มี timestamp, จำกัดช่วง, จำกัดอัตราเปลี่ยน)
SLOW LOOP (5-20 Hz)
   anomaly detector (efference copy จาก CPG เทียบกับเซนเซอร์) -> stimulus
   -> AHM (ฮอร์โมนเทียม) -> receptor
   -> event arbiter (priority + timestamp) -> Behavior/Emotion FSM (+ State Guard)
   -> ไฟ / เสียง / จอ
```

**กฎหลัก 5 ข้อ**

1. คนเขียนคำสั่งมอเตอร์มีคนเดียว คือ Actuator Safety Interface ใน fast loop
2. AHM และ FSM ส่งได้แค่ "พารามิเตอร์" ผ่าน Bounded Modulation Interface ห้ามสั่งมอเตอร์ตรง
3. ความปลอดภัยหลัก (reflex, actuator safety, watchdog, E-stop) ต้องทำงานได้แม้ AHM หรือ FSM พัง
4. ข้อมูลเสียไม่เท่ากับปกติ ทุกจุดต้องแยก "ไม่รู้" ออกจาก "ปกติ"
5. ทุกการเปลี่ยนแปลงต้องนุ่ม (filter, hysteresis, slew-rate) ยกเว้นการหยุดฉุกเฉิน

---

## 2. หลักชีววิทยาที่ใช้

| ในสัตว์ | ในหุ่น | ใช้แก้อะไร |
|---|---|---|
| Exteroception (ตา, หู, เส้นข้างลำตัว) | เซนเซอร์ระยะ, กล้อง, pressure sensor | รู้ว่าข้างนอกมีอะไร |
| Proprioception (muscle spindle, Golgi tendon organ, vestibular) | encoder, force/tactile, IMU, กระแสมอเตอร์ | รู้ว่าตัวเองอยู่ท่าไหน เท้าแตะพื้นไหม |
| CPG ในไขสันหลัง / ปมประสาท | วงจรออสซิลเลเตอร์ (SO(2), coupled oscillators) | ลดมิติการควบคุม สร้างท่าเดินเป็นจังหวะ |
| รีเฟล็กซ์ (เช่น elevator reflex) | phase resetting, elevator reflex จาก feedback | ปรับตัวเมื่อเจอหลุมหรือสิ่งกีดขวาง |
| ระบบประสาท (เร็ว, ms) กับฮอร์โมน (ช้า, วินาทีถึงนาที) | fast loop กับ AHM ใน slow loop | ความจำเชิงเวลา ไม่กระชากไปมา |
| Efference copy + internal forward model | เทียบ expected กับ actual feedback | ตรวจจับความผิดปกติ |
| สภาวะภายใน (กลัว, หิว, อยากรู้) | Internal State FSM | พฤติกรรมขึ้นกับบริบท |

---

## 3. ชั้นรับรู้และปรับสภาพสัญญาณ (fast loop)

ลำดับ: validate -> low-pass filter -> hysteresis (ค่าต่อเนื่อง) หรือ debounce (ค่าใช่/ไม่ใช่) -> ใช้ตัดสินใจ

- **validate**: เช็ค NaN/inf, ช่วงวัด (รวมค่าขอบที่แปลว่าเสีย เช่น 0 หรือ 65535), timeout (ไม่มีค่ามา), stale (timestamp เก่า) และสำหรับเซนเซอร์ที่ควรขยับตลอด ให้เช็คด้วยว่าค่าค้างเท่าเดิมนานผิดปกติไหม ค่าเสียห้ามเข้า filter เพราะ filter จะให้ค่าผิดต่อไปอีกหลายรอบ
- **low-pass filter**: ลด noise ความถี่สูง
- **hysteresis**: ใช้สองเกณฑ์ (เข้า/ออก) กัน chattering จาก single threshold
- **debounce**: ต้องได้ค่าเดิมติดกัน n รอบถึงจะเชื่อ
- **trade-off**: ทุกชั้นเพิ่ม latency ต้องตั้งให้หน่วงน้อยพอเทียบกับความเร็วของสิ่งที่เข้ามา และมีเกณฑ์ฉุกเฉิน (เช่น ใกล้มากจริงๆ) ที่ข้าม filter ได้
- ข้อมูลเสียนานเกินกำหนด -> safe fallback (หัวข้อ 13)

```python
import math
import statistics
from dataclasses import dataclass


@dataclass
class Sample:
    value: float
    timestamp: float   # วินาที จากนาฬิกาที่ซิงค์กันทุกบอร์ด


def validate(sample, now, lo, hi, stale_limit, invalid_values=()):
    """คืนค่า float ถ้าใช้ได้, คืน None ถ้าเสีย (ห้ามส่ง None หรือค่าเสียเข้า filter)"""
    if sample is None:
        return None                          # timeout: ไม่มีข้อมูลมา
    v = sample.value
    if v is None or not math.isfinite(v):
        return None                          # NaN / inf
    if v in invalid_values or not (lo <= v <= hi):
        return None                          # ค่าที่เป็นไปไม่ได้ หรือค่าขอบที่แปลว่าเสีย (เช่น 0, 65535)
    if now - sample.timestamp > stale_limit:
        return None                          # stale: ค่าเก่าเกินไป
    return v


class LowPass:
    """y += a * (x - y) ; a เล็ก = เรียบมากแต่ช้า (latency มาก)"""
    def __init__(self, a):
        assert 0.0 < a <= 1.0
        self.a, self.y = a, None

    def update(self, x):
        self.y = x if self.y is None else self.y + self.a * (x - self.y)
        return self.y


class Hysteresis:
    """active เมื่อค่า < enter_below และปล่อยเมื่อค่า > release_above (เช่น ระยะสิ่งกีดขวาง)"""
    def __init__(self, enter_below, release_above):
        assert release_above > enter_below
        self.enter_below, self.release_above = enter_below, release_above
        self.active = False

    def update(self, x):
        if not self.active and x < self.enter_below:
            self.active = True
        elif self.active and x > self.release_above:
            self.active = False
        return self.active


class Debounce:
    """เปลี่ยนสถานะเมื่อได้ค่าใหม่ติดกัน n รอบ"""
    def __init__(self, n, initial=False):
        self.n, self.state, self.count = n, initial, 0

    def update(self, raw):
        if raw != self.state:
            self.count += 1
            if self.count >= self.n:
                self.state, self.count = raw, 0
        else:
            self.count = 0
        return self.state
```

---

## 4. CPG (fast loop)

### 4.1 SO(2) oscillator

```
o1(t+1) = tanh( w11*o1(t) + w12*o2(t) )
o2(t+1) = tanh( w21*o1(t) + w22*o2(t) )
w11 = w22 = alpha*cos(phi),  w12 = alpha*sin(phi),  w21 = -alpha*sin(phi)
```

ผลทดสอบตอนเขียนไฟล์นี้ (1 รอบ = 1 step ของ CPG):

- alpha = 1.01 แกว่งแบบเกือบ sine แอมพลิจูดของ o1, o2 ประมาณ 0.2 คาบประมาณ 2π/phi รอบ (phi = 0.1 ได้ราว 63 รอบ) และ o2 นำ o1 ราว 90 องศา (o2 > 0 ตรงกับช่วงที่ o1 กำลังเพิ่ม ประมาณ 94-99% ของเวลา)
- alpha สูง (เช่น 1.4 กับ phi = 0.1) วงจรหยุดแกว่งและค้างที่ค่าคงที่ ส่วนที่ phi อื่นคาบเพี้ยนไปจาก 2π/phi มาก จึงควรใช้ alpha ใกล้ 1 แล้วไปปรับขนาดการเคลื่อนไหวที่ decoder แทน
- ห้ามเริ่มที่ (0, 0) เพราะจะไม่แกว่งเลย
- ความถี่ก้าว (Hz) ประมาณ `phi / (2π * dt)` โดย dt คือเวลาต่อ 1 step

### 4.2 Decoder สำหรับ alternating tripod (กรณีหุ่น 6 ขา)

- กลุ่ม A: L1, R2, L3 / กลุ่ม B: R1, L2, R3 โดยกลุ่ม B ใช้ -o1, -o2 (ต่างเฟส 180 องศา)
- o1 -> TC joint: o1 เพิ่ม = protraction (แกว่งไปหน้า), o1 ลด = retraction (ดึงไปหลัง)
- o2 -> CTr joint: o2 > 0 = swing (ยกขา), o2 <= 0 = stance (วางขาค้ำ)
- ฝั่งซ้ายกับขวาอาจต้องกลับเครื่องหมายตามทิศการติดตั้งมอเตอร์
- ถ้าหุ่นไม่ใช่ 6 ขา ใช้หลักเดียวกัน คือกำหนดความต่างเฟสระหว่างขาหรือปล้อง เช่น 4 ขาแบบ trot ให้ขาทแยง FL-HR กับ FR-HL ต่างเฟส 180 องศา หรือว่ายแบบ anguilliform ให้มี phase lag คงที่จากหัวไปหาง

### 4.3 Frequency กับ amplitude

- **ความถี่ (phi)**: ก้าวถี่ขึ้นแต่ความยาวก้าวเท่าเดิม เหมาะกับพื้นเรียบที่อยากเร็วขึ้นหรือช้าลง ถ้าสูงเกิน มอเตอร์ตามไม่ทัน ช่วง stance สั้นลง หุ่นลื่นหรือเสียการทรงตัว
- **amplitude/gain (ใน decoder)**: ก้าวยาวขึ้นและยกขาสูงขึ้น เหมาะกับพื้นขรุขระ โคลน และการปีนลาด แต่ใช้แรงบิดและพลังงานมากขึ้น และอาจชนขีดจำกัดข้อต่อ
- ความเร็วเดินประมาณ ความยาวก้าว x ความถี่
- ปีนลาดชันให้เพิ่ม amplitude/แรง ไม่ใช่เร่งความถี่

### 4.4 Closed-loop CPG (feedback)

| เหตุการณ์ | ข้อมูลที่กระตุ้น | การตอบสนอง |
|---|---|---|
| แตะพื้นก่อนเวลา | force/tactile ที่เท้า ในช่วง swing | phase resetting เข้า stance |
| ถึงช่วง stance แต่ไม่เจอพื้น (หลุม) | ไม่มีแรงกด + IMU เอียงไปทางขานั้น | หน่วงเฟส ยืดขาหาพื้น ห้ามกลุ่มขาอื่นยกขึ้น |
| ชนสิ่งกีดขวางตอนแกว่งขา | tactile ด้านหน้าขา + กระแสพุ่ง ในช่วง swing | elevator reflex ยกขาสูงชั่วคราวแล้วก้าวข้าม |
| ตัวเอียงมาก | IMU | ลดความถี่ หรือหยุดจนตัวกลับมาตรง |

กันการตอบสนองผิดจากสัญญาณรบกวน: hysteresis + debounce, phase gating (รับสัญญาณเฉพาะช่วงเฟสที่สมเหตุสมผล), ยืนยันด้วยสองเซนเซอร์, refractory period (reflex เดียวกันห้ามเกิดซ้ำถี่เกิน), จำกัดการเลื่อนเฟสต่อก้าว และถ้าข้อมูลเสียให้เลิกใช้ feedback ชั่วคราวแล้วเดินช้าลง

หมายเหตุ: ถ้าใช้ CPG ตัวเดียวคุมทุกขา การหน่วงเฟสจะหน่วงทั้งระบบ (หยุดหมุน CPG) ถ้าอยากหน่วงทีละขา ต้องใช้ CPG ต่อขาที่ต่อกันแบบ coupled oscillators

```python
class SO2CPG:
    """o1' = tanh(w11*o1 + w12*o2), o2' = tanh(w21*o1 + w22*o2)
    w11 = w22 = alpha*cos(phi), w12 = alpha*sin(phi), w21 = -alpha*sin(phi)"""
    def __init__(self, phi=0.1, alpha=1.01):
        self.phi, self.alpha = phi, alpha
        self.o1, self.o2 = 0.1, 0.0           # ห้ามเริ่มที่ (0, 0) ไม่งั้นไม่แกว่ง
        self.frozen = False                   # True = หน่วงเฟสทั้งระบบชั่วคราว (เช่น ขาหาพื้นไม่เจอ)

    def step(self):
        if not self.frozen:
            c = self.alpha * math.cos(self.phi)
            s = self.alpha * math.sin(self.phi)
            self.o1, self.o2 = (math.tanh(c * self.o1 + s * self.o2),
                                math.tanh(-s * self.o1 + c * self.o2))
        return self.o1, self.o2


def phi_for_frequency(freq_hz, dt):
    """ความถี่ก้าว (Hz) -> phi ; dt = เวลาต่อ 1 step ของ CPG"""
    return 2.0 * math.pi * freq_hz * dt


GROUP_A = ("L1", "R2", "L3")
GROUP_B = ("R1", "L2", "R3")


def decode_tripod(o1, o2, amp_tc, amp_lift, norm=0.2, mirror_right=True):
    """คืน {ขา: (มุม TC, มุม CTr)} ; norm = แอมพลิจูดจริงของ o1/o2 (alpha = 1.01 ได้ราว 0.2)"""
    out = {}
    for leg in GROUP_A + GROUP_B:
        sign = 1.0 if leg in GROUP_A else -1.0      # กลุ่ม B กลับเฟส 180 องศา
        x1, x2 = sign * o1 / norm, sign * o2 / norm
        tc = amp_tc * x1                            # o1 เพิ่ม = protraction, ลด = retraction
        if mirror_right and leg.startswith("R"):
            tc = -tc                                # ฝั่งขวาติดมอเตอร์กลับด้าน (เช็คกับหุ่นจริง)
        lift = amp_lift * max(x2, 0.0)              # o2 > 0 = swing (ยกขา), <= 0 = stance
        out[leg] = (tc, lift)
    return out


class LegFeedback:
    """ตัดสินใจ reflex ของขาหนึ่งข้าง เรียกทุกรอบ fast loop
    o2_leg = o2 ของขานั้นหลังคูณเครื่องหมายกลุ่มแล้ว (กลุ่ม B = -o2)
    foot_contact = ผ่าน validate + filter + hysteresis มาแล้ว (True = เท้ามีแรงกด)"""
    def __init__(self, contact_n=3, hit_n=2):
        self.contact = Debounce(contact_n)
        self.hit = Debounce(hit_n)

    def update(self, o2_leg, foot_contact, front_touch, current_spike, stance_started_long_enough):
        contact = self.contact.update(foot_contact)
        hit = self.hit.update(front_touch and current_spike)      # ยืนยันด้วยสองเซนเซอร์
        swing = o2_leg > 0.0
        if swing and hit:
            return "ELEVATOR_REFLEX"        # ชนระหว่างแกว่ง -> ยกขาสูงชั่วคราวแล้วก้าวข้าม
        if swing and contact:
            return "EARLY_CONTACT_RESET"    # แตะพื้นก่อนเวลา -> รีเซ็ตเฟสเข้า stance
        if not swing and stance_started_long_enough and not contact:
            return "SEARCH_HOLD_PHASE"      # ถึงช่วง stance แต่ไม่เจอพื้น -> หน่วงเฟส ยืดขาหาพื้น
        return None
```

---

## 5. Artificial Hormone Mechanism (AHM) — หัวใจของหุ่นตัวนี้

### 5.1 สมการ

H อยู่ในช่วง [0, 1] อัปเดตทุกรอบ slow loop

```
H <- clamp( H + alpha*S*(1 - H) - beta*H - gamma*H , 0, 1 )
```

S คือ stimulus ระดับ 0 ถึง 1 (ระดับความเสี่ยงหรือสิ่งเร้า ที่ผ่าน validate แล้ว)

| ส่วนประกอบ | สัญลักษณ์ | หน้าที่ | ตั้งสูงเกิน | ตั้งต่ำเกิน |
|---|---|---|---|---|
| Production | alpha | ความไวในการสะสมเมื่อเจอสิ่งเร้า | ชนเพดานง่าย แยกระดับอันตรายไม่ได้ | ฮอร์โมนแทบไม่ขึ้น ไม่ตอบสนอง |
| Clearance | beta | ความเร็วในการลืม กลับสู่ปกติ | ลืมเร็ว กลับไปกระชากไปมาเหมือนไม่มีความจำ | ค้างนาน ฟื้นตัวช้า |
| Receptor Binding | gamma | ตัวรับแปลง H เป็นผลต่อพฤติกรรม และดึงฮอร์โมนที่ใช้แล้วออก | ผลหมดเร็ว | ฮอร์โมนค้าง |
| Saturation Bounds | [0, 1] | กันค่าติดลบหรือพุ่งไม่จำกัด | - | ไม่มี bounds = ค่าพุ่งไม่หยุด |

- เทอม (1 - H) คือ soft saturation ยิ่งใกล้เพดานยิ่งสร้างได้น้อย ค่าเลยไม่กระแทกเพดาน
- clamp ทุกรอบ ห้ามเก็บส่วนที่เกินเพดานไว้ ไม่งั้นส่วนเกินจะกลายเป็นหนี้ที่ต้องรอสลาย ฟื้นช้าลงอีก

### 5.2 สูตรช่วยจูน (ตรวจกับการจำลองแล้ว)

- ค่าที่ H จะนิ่งอยู่เมื่อ S คงที่: `H* = alpha*S / (alpha*S + beta + gamma)` (ถ้าไม่มีเทอม (1 - H) จะได้ `alpha*S / (beta + gamma)` ซึ่งเกิน 1 ได้ = ชนเพดาน)
- ครึ่งชีวิตตอนไม่มีสิ่งเร้า: `n_half = ln(0.5) / ln(1 - (beta + gamma))` รอบ ประมาณ `ln2 / (beta + gamma)`
- ตอนมีสิ่งเร้า H วิ่งเข้าหา H* ด้วยอัตรา `(alpha*S + beta + gamma)` ต่อรอบ จึงขึ้นเร็วกว่าลง (ตื่นตัวไว ลืมช้า) ซึ่งเป็นพฤติกรรมที่ต้องการ
- ขั้นตอนจูน
  1. เลือกครึ่งชีวิตที่อยากได้ -> ได้ beta + gamma
  2. เลือก H* ที่อยากได้ตอนอันตรายระดับปกติ (เช่น 0.6-0.7 เหลือที่ว่างด้านบนไว้แยกอันตรายที่หนักกว่า) -> ได้ `alpha = H* (beta + gamma) / (S (1 - H*))`
  3. แบ่ง beta กับ gamma (gamma คือส่วนที่ถูกใช้ไปตามการออกฤทธิ์)
- ตัวอย่าง: slow loop 10 Hz (dt = 0.1 s) อยากได้ครึ่งชีวิต 2 วินาที -> beta + gamma ประมาณ 0.034 และอยากให้ H* = 0.7 ที่ S = 1 -> alpha ประมาณ 0.08
- alpha และ beta + gamma ต้องน้อยกว่า 1 มากๆ ต่อรอบ ไม่งั้นค่ากระโดด
- ช่วงที่สิ่งเร้าหายไปแป๊บเดียว (เช่น 0.2 วินาทีหลังโขดหิน) ต้องสั้นกว่าครึ่งชีวิตมาก H จะได้ไม่ตก

### 5.3 สิ่งเร้า (stimulus)

- ไล่ระดับ 0 ถึง 1 ตามความรุนแรง ไม่ใช่แค่ 0 หรือ 1
- หลายแหล่งรวมด้วย max() หรือถ่วงน้ำหนักแล้ว clamp
- แหล่งที่ใช้ได้: ระยะสิ่งกีดขวาง, reflex ที่เกิดถี่, ผลจาก anomaly detector (หัวข้อ 8), ความเอียงจาก IMU, การสั่นของพื้น
- ข้อมูลเสียไม่เอาไปสร้างฮอร์โมน (หัวข้อ 7)

### 5.4 หลายฮอร์โมน (ถ้าต้องการ)

- ฮอร์โมนแต่ละตัวมี alpha, beta, gamma ของตัวเอง เช่น caution (ระวังภัย), fatigue (ล้า/พลังงานต่ำ), curiosity (อยากสำรวจ)
- แต่ละตัวมีตัวรับไปที่พารามิเตอร์ของตัวเอง ถ้าสองฮอร์โมนปรับพารามิเตอร์เดียวกัน ให้ตัดสินที่ Bounded Modulation Interface (เช่น เลือกทางที่ปลอดภัยกว่า) แล้ว clamp อีกรอบ
- ระวังฮอร์โมนกระตุ้นกันเองเป็นวง (positive feedback) จนค้างเพดาน

### 5.5 Receptor

- แปลง H เป็น effect 0 ถึง 1 แบบต่อเนื่อง มี threshold (H ต่ำกว่านี้ไม่มีผล) และ sensitivity
- ตัวรับแต่ละตัวไวต่างกันได้ เช่น ความเร็วเดินเริ่มลดตั้งแต่ H น้อยๆ แต่ความสูงยกขาเปลี่ยนเมื่อ H สูงแล้ว

```python
class Hormone:
    """H ใน [0, 1] ; อัปเดตทุกรอบ slow loop
    H <- clamp( H + alpha*S*(1-H) - beta*H - gamma*H , 0, 1 )"""
    def __init__(self, name, alpha, beta, gamma):
        assert 0.0 < alpha < 1.0 and beta >= 0.0 and gamma >= 0.0 and beta + gamma < 1.0
        self.name, self.alpha, self.beta, self.gamma = name, alpha, beta, gamma
        self.h = 0.0
        self.last_update = None

    def update(self, stimulus, now):
        s = min(max(stimulus, 0.0), 1.0)                 # stimulus ต้องผ่าน validate มาแล้ว
        production = self.alpha * s * (1.0 - self.h)     # soft saturation: ใกล้เพดานยิ่งสร้างน้อย
        clearance = self.beta * self.h
        binding = self.gamma * self.h
        self.h = min(max(self.h + production - clearance - binding, 0.0), 1.0)  # clamp ทุกรอบ
        self.last_update = now
        return self.h

    def reset(self, value=0.0):
        self.h = value

    def equilibrium(self, s):
        """ค่าที่ H จะนิ่งอยู่เมื่อ stimulus คงที่ = s"""
        return self.alpha * s / (self.alpha * s + self.beta + self.gamma)

    def half_life_steps(self):
        """จำนวนรอบที่ H ลดลงครึ่งหนึ่งเมื่อไม่มีสิ่งเร้า"""
        k = self.beta + self.gamma
        return math.inf if k == 0 else math.log(0.5) / math.log(1.0 - k)


def decay_rate_for_half_life(half_life_s, dt):
    """คืนค่า beta + gamma ที่ให้ครึ่งชีวิตตามต้องการ ; dt = เวลาต่อรอบ slow loop"""
    n = half_life_s / dt
    return 1.0 - 0.5 ** (1.0 / n)


def alpha_for_equilibrium(h_target, s, k):
    """คืน alpha ที่ทำให้ H นิ่งที่ h_target เมื่อ stimulus = s ; k = beta + gamma"""
    assert 0.0 < h_target < 1.0 and s > 0.0
    return h_target * k / (s * (1.0 - h_target))


def receptor(h, sensitivity=1.0, threshold=0.0):
    """แปลง H -> effect 0..1 ; H ต่ำกว่า threshold ไม่มีผล"""
    assert 0.0 <= threshold < 1.0
    if h <= threshold:
        return 0.0
    return min(1.0, sensitivity * (h - threshold) / (1.0 - threshold))


# ตัวอย่างการตั้งค่า: slow loop 10 Hz, ครึ่งชีวิต 2 วินาที, H* = 0.7 เมื่อ S = 1
k = decay_rate_for_half_life(2.0, 0.1)            # ประมาณ 0.034
alpha = alpha_for_equilibrium(0.7, 1.0, k)        # ประมาณ 0.08
caution = Hormone("caution", alpha, beta=0.7 * k, gamma=0.3 * k)
```

---

## 6. Bounded Modulation Interface

- รับ effect จาก receptor -> แปลงเป็นค่าพารามิเตอร์ระหว่าง "ค่าปกติ" กับ "ค่าเมื่อผลเต็มที่" -> clamp ในช่วงปลอดภัย -> จำกัดอัตราเปลี่ยนต่อรอบ -> ส่งให้ CPG พร้อม timestamp
- ต่อให้ H ค้างที่ 1 หุ่นก็ทำได้แค่ค่าสุดขอบที่อนุญาต ไม่หยุดนิ่ง ไม่ทำท่าอันตราย
- ปรับได้แค่พารามิเตอร์ ไม่มีสิทธิ์สั่งมอเตอร์หรือข้ามชั้น safety
- ที่ต้องผ่าน CPG เพราะ CPG คุมให้ทุกข้อต่อประสานกัน ถ้าฮอร์โมนไปสั่งมอเตอร์เอง จังหวะการเดินจะพัง

| พารามิเตอร์ (ตัวอย่าง) | ค่าปกติ (effect 0) | ค่าเมื่อผลเต็มที่ (effect 1) | ช่วงปลอดภัย |
|---|---|---|---|
| ตัวคูณความถี่ CPG | 1.0 | 0.5 | 0.4-1.1 |
| ตัวคูณความสูงยกขา | 1.0 | 1.3 | 0.8-1.4 |
| ระยะเริ่มหลบสิ่งกีดขวาง | 0.4 m | 0.7 m | 0.3-0.8 m |

```python
@dataclass
class ModulatedParam:
    normal: float        # ค่าเมื่อ effect = 0
    full: float          # ค่าเมื่อ effect = 1
    safe_min: float
    safe_max: float
    max_step: float      # เปลี่ยนได้สูงสุดต่อรอบ (slew-rate ของพารามิเตอร์)
    value: float = None

    def _move_toward(self, target):
        target = min(max(target, self.safe_min), self.safe_max)      # bounds
        if self.value is None:
            self.value = min(max(self.normal, self.safe_min), self.safe_max)
        step = min(max(target - self.value, -self.max_step), self.max_step)
        self.value += step
        return self.value

    def update(self, effect):
        e = min(max(effect, 0.0), 1.0)
        return self._move_toward(self.normal + e * (self.full - self.normal))

    def force_safe(self, safe_value):
        """ใช้ตอน fault: ค่อยๆ ไปที่ค่าปลอดภัย (ยังจำกัดอัตราเปลี่ยนอยู่)"""
        return self._move_toward(safe_value)


params = {
    "freq_scale": ModulatedParam(normal=1.0, full=0.5, safe_min=0.4, safe_max=1.1, max_step=0.02),
    "lift_scale": ModulatedParam(normal=1.0, full=1.3, safe_min=0.8, safe_max=1.4, max_step=0.02),
}
```

---

## 7. AHM fault handling (software fault fallback)

- ตรวจ: ค่า H เป็น NaN หรือหลุดช่วง, โมดูลไม่อัปเดตเกินเวลาที่กำหนด (หยุดเงียบ), H ค้างเพดานทั้งที่ไม่มีสิ่งเร้ามานาน, เซนเซอร์ต้นทางค้างค่าสูงสุด (จับที่ validate ตั้งแต่หัวข้อ 3)
- เมื่อพบ: แจ้งเตือนทันที (ห้ามพังเงียบ) -> interface เลิกใช้ค่าจาก AHM -> ใช้ safe default ของภารกิจ -> รีเซ็ตโมดูลและล้างค่า H
- safe default ต้องเลือกตามภารกิจ หุ่นในพื้นที่เสี่ยง (ซากอาคาร อุโมงค์) ควรเป็น "เดินช้าระวังตัว" ไม่ใช่ "เดินเร็ว"
- การล้าง H เป็น 0 ไม่ได้แปลว่ากลับไปเดินเร็ว เพราะระหว่าง fault ใช้ safe default ไม่ได้ใช้ค่าจาก H
- AHM ต้องไม่ใช่ตัวคุมความปลอดภัยหลัก ถ้า AHM พัง หุ่นต้องยังปลอดภัย

```python
def ahm_health(hormone, now, quiet_time, timeout, stuck_time):
    """quiet_time = เวลาที่ไม่มีสิ่งเร้าต่อเนื่อง (วินาที)"""
    h = hormone.h
    if h is None or not math.isfinite(h) or not (0.0 <= h <= 1.0):
        return "FAULT_VALUE"
    if hormone.last_update is None or now - hormone.last_update > timeout:
        return "FAULT_STALE"          # โมดูลหยุดอัปเดตแบบเงียบๆ
    if h > 0.95 and quiet_time > stuck_time:
        return "FAULT_STUCK"          # ไม่มีสิ่งเร้ามานาน แต่ H ยังค้างเพดาน
    return "OK"


SAFE_DEFAULT = {"freq_scale": 0.6, "lift_scale": 1.1}   # กำหนดตามภารกิจ (พื้นที่เสี่ยง = เดินช้าระวังตัว)


def modulation_step(hormone, params, now, quiet_time, alert):
    """เรียกทุกรอบ slow loop ; คืน (ค่าพารามิเตอร์ที่จะส่งให้ CPG, สถานะ)"""
    status = ahm_health(hormone, now, quiet_time, timeout=0.5, stuck_time=10.0)
    if status != "OK":
        alert(f"AHM {hormone.name}: {status}")            # ห้ามพังเงียบ
        hormone.reset(0.0)                                 # ล้างค่า (ระหว่างนี้ใช้ safe default)
        return {name: p.force_safe(SAFE_DEFAULT[name]) for name, p in params.items()}, status
    effect = receptor(hormone.h, sensitivity=1.0, threshold=0.1)
    return {name: p.update(effect) for name, p in params.items()}, status
```

---

## 8. Anomaly detector (efference copy) -> stimulus ของ AHM

- **forward model** รับสำเนาคำสั่งจริงจาก CPG (ห้ามใช้ตารางท่าเดินตายตัว ไม่งั้นเปลี่ยนท่าเดินแล้วแจ้งผิดปกติ) แล้วทำนาย expected feedback ทั้งมุมข้อต่อ แรงกดเท้า กระแสมอเตอร์ และความเร็วลำตัว (ประมาณจากความยาวก้าว x ความถี่)
- **actual feedback** มาจาก encoder, force/tactile, กระแสมอเตอร์ และ IMU
- เทียบแค่ "ขาขยับตามคำสั่งไหม" ไม่พอ เพราะมอเตอร์คุมมุมตัวเองได้อยู่แล้ว ต่อให้ขาลื่นหรือลอยอยู่ต้องเช็คผลระดับลำตัวด้วย
- **time alignment**: ค่าจริงมาช้ากว่าคำสั่งเสมอ (มอเตอร์ เฟือง driver การสื่อสาร filter ความเฉื่อย) วัดดีเลย์ตอนเดินปกติ เลื่อน expected ก่อนเทียบ จับคู่ด้วย timestamp ไม่ใช่ลำดับ และวัดใหม่เป็นระยะ ยิ่งเดินเร็วยิ่งสำคัญเพราะดีเลย์เท่าเดิมแต่หนึ่งก้าวสั้นลง
- **sanitizer** ก่อนเข้า sliding window คำนวณเฉพาะค่าดี และต้องมีค่าดีอย่างน้อยราว 80% ของหน้าต่าง ไม่งั้นผลคือ "ข้อมูลไม่พอ" ซึ่งห้ามนับว่าปกติ (NaN ตัวเดียวทำให้ผลรวมทั้งหน้าต่างเป็น NaN จนกว่าจะเลื่อนหลุด จึงต้องกรองก่อนเข้า)
- **ตัวชี้วัด**
  - MAE ต่อขา: วัดขนาดตรงๆ จับกรณี gain/offset ที่ correlation มองไม่เห็น
  - correlation: ดูรูปร่างและจังหวะ มีด่าน SD ต่ำกว่า eps ไม่คำนวณ (กันหารศูนย์) แล้วติดป้ายว่าสัญญาณแบน
  - Global Inconsistency (MAE เฉลี่ยทุกขา): จับ common-mode failure ที่ทุกขาผิดพร้อมกัน ซึ่ง SD ระหว่างขามองไม่เห็น
  - SD ระหว่างขา: จับกรณีบางขาผิด
  - IMU Stall Detector: CPG สั่งเดินแต่ตัวไม่ไปนานเกินเวลาที่กำหนด
- ผลส่งเป็น stimulus ของ AHM หรือเป็นเหตุการณ์ให้ FSM ไม่สั่งมอเตอร์ตรง

```python
EPS = 1e-6   # ตั้งเป็นหน่วยจริงของสัญญาณ (เช่น 0.05 N) ไม่ใช่ศูนย์พอดี


def estimate_delay(expected, actual, max_lag):
    """หาค่า lag (จำนวน sample) ที่ทำให้ actual ตรงกับ expected ที่สุด ใช้ตอนเดินปกติ"""
    best_lag, best_err = 0, math.inf
    for lag in range(max_lag + 1):
        pairs = list(zip(expected[:len(expected) - lag], actual[lag:]))
        if not pairs:
            break
        err = sum(abs(e - a) for e, a in pairs) / len(pairs)
        if err < best_err:
            best_lag, best_err = lag, err
    return best_lag


def window_metrics(expected, actual, min_valid_ratio=0.8, eps=EPS):
    """expected/actual = ลิสต์ที่จับคู่ด้วย timestamp แล้ว (หลัง time alignment) ; ค่าเสีย = None"""
    pairs = [(e, a) for e, a in zip(expected, actual) if e is not None and a is not None]
    if not expected or len(pairs) < min_valid_ratio * len(expected):
        return None                                   # ข้อมูลไม่พอ: ห้ามนับว่าปกติ
    es = [p[0] for p in pairs]
    acts = [p[1] for p in pairs]
    mae = sum(abs(e - a) for e, a in pairs) / len(pairs)
    sd_e, sd_a = statistics.pstdev(es), statistics.pstdev(acts)
    if sd_e < eps or sd_a < eps:
        corr = None                                   # สัญญาณแบน: ไม่คำนวณ (กันหารศูนย์)
    else:
        me, ma = statistics.fmean(es), statistics.fmean(acts)
        cov = sum((e - me) * (a - ma) for e, a in pairs) / len(pairs)
        corr = cov / (sd_e * sd_a)
    return {"mae": mae, "corr": corr, "flat": sd_a < eps}


def classify(leg_metrics, cmd_speed, imu_speed, stall_duration, th):
    """leg_metrics = {ขา: ผลจาก window_metrics} ; th = เกณฑ์ (จูนจากการทดสอบจริง)"""
    stalled = cmd_speed > th["v_cmd_min"] and imu_speed < th["v_stall"]
    if stalled and stall_duration > th["stall_time"]:
        return "STALL"                                # สั่งเดินแต่ตัวไม่ไป (actuator ค้าง ท้องค้าง หรือลื่นหมด)
    if any(m is None for m in leg_metrics.values()):
        return "INSUFFICIENT_DATA"
    maes = [m["mae"] for m in leg_metrics.values()]
    global_mae = sum(maes) / len(maes)                # Global Inconsistency
    spread = statistics.pstdev(maes)                  # ความต่างระหว่างขา
    if global_mae > th["global_mae"]:
        return "COMMON_MODE"                          # ผิดพร้อมกันทั้งระบบ แม้ spread จะต่ำ
    bad = [leg for leg, m in leg_metrics.items()
           if m["mae"] > th["leg_mae"] or (m["corr"] is not None and m["corr"] < th["corr_min"])]
    if bad or spread > th["spread"]:
        return "LOCAL"
    return "NORMAL"


ANOMALY_TO_STIMULUS = {"NORMAL": 0.0, "LOCAL": 0.4, "COMMON_MODE": 0.8, "STALL": 1.0}
# INSUFFICIENT_DATA ไม่ส่งเข้าฮอร์โมน: นับเวลาไว้ ถ้านานเกินกำหนด -> safe fallback (หัวข้อ 13)
```

---

## 9. Event arbiter และ race condition

- **race condition**: เหตุการณ์ที่มาด้วยอัตราต่างกัน (เช่น โหมดไฟที่คิดจากข้อมูลช้า กับเหตุการณ์ด่วนจาก tactile) แย่งกันเปลี่ยนสถานะ ใครถูกประมวลผลทีหลังชนะ ใน simulation ไม่เจอเพราะเหตุการณ์มาตามลำดับเดิมทุกครั้ง แต่บนฮาร์ดแวร์ลำดับสลับกันได้
- **วิธีแก้**
  - ทุกเหตุการณ์ติด timestamp ของ "ข้อมูลที่ใช้ตัดสิน" และทุกบอร์ดใช้นาฬิกาที่ซิงค์กัน
  - เหตุการณ์ทุกตัวเข้าทางเดียว (arbiter) เลือกตาม priority
  - ทิ้งเหตุการณ์ที่คิดจากข้อมูลเก่ากว่าการเปลี่ยนสถานะล่าสุด (ยกเว้นระดับความปลอดภัย) แล้วรอค่าใหม่รอบหน้า
  - State Guard ในแต่ละสถานะ (หัวข้อ 10) เพราะ priority อย่างเดียวเทียบได้แค่เหตุการณ์ที่มาในรอบเดียวกัน
  - เหตุการณ์ที่เป็น "สภาวะ" (battery_low, hazard) ให้ต้นทางส่งซ้ำทุกรอบตราบใดที่ยังจริง จะได้ไม่หายไปตอนถูก guard บล็อก
  - reflex ทำใน fast loop ไม่ต้องรอ FSM อนุญาต
  - single writer: มอเตอร์มีทางเข้าทางเดียว ไฟเขียนได้แค่ไฟ FSM/AHM เขียนได้แค่พารามิเตอร์
  - slew-rate ทุกช่องทางออก (คำสั่งข้อต่อ, พารามิเตอร์ CPG, สีและความสว่างของไฟ)
- **priority ตัวอย่าง** (เลขน้อย = สำคัญกว่า): 0 E-stop (ฮาร์ดแวร์), 1 hazard / actuator fault, 2 reflex, 3 anomaly, 4 พฤติกรรมและการแสดงผล, 5 battery_low

```python
PRIORITY = {               # เลขน้อย = สำคัญกว่า (E-stop จริงอยู่ที่ฮาร์ดแวร์ ไม่ผ่านโค้ดนี้)
    "estop": 0,
    "hazard": 1, "hazard_clear": 1, "actuator_fault": 1,
    "reflex": 2,
    "anomaly": 3,
    "target_seen": 4, "target_confirmed": 4, "target_lost": 4,
    "handoff_done": 4, "charged": 4,
    "battery_low": 5,
}


@dataclass
class Event:
    kind: str
    timestamp: float     # เวลาของ "ข้อมูล" ที่ใช้ตัดสินเหตุการณ์นี้ ไม่ใช่เวลาที่มาถึง
    priority: int = None

    def __post_init__(self):
        if self.priority is None:
            self.priority = PRIORITY[self.kind]


class Arbiter:
    def __init__(self, stale_limit):
        self.stale_limit = stale_limit
        self.last_state_change = -math.inf

    def mark_state_change(self, now):
        self.last_state_change = now

    def candidates(self, events, now, allowed_max_priority):
        """คืนเหตุการณ์ที่ใช้ได้ เรียงตาม priority (ถ้าเท่ากัน เอาข้อมูลใหม่กว่าก่อน)"""
        valid = []
        for e in events:
            is_safety = e.priority <= 1
            stale = (now - e.timestamp > self.stale_limit) or (e.timestamp < self.last_state_change)
            if stale and not is_safety:
                continue                     # คิดจากข้อมูลเก่า -> ทิ้ง รอค่าใหม่รอบหน้า (กัน race condition)
            if e.priority <= allowed_max_priority:
                valid.append(e)              # ผ่าน State Guard
        return sorted(valid, key=lambda e: (e.priority, -e.timestamp))
```

---

## 10. Behavior / Emotion FSM

Template 5 สถานะ (ปรับชื่อและความหมายตามภารกิจของหุ่นตัวใหม่)

| สถานะ | เข้าเมื่อ | พฤติกรรม | การแสดงผล (ถ้ามีไฟ/เสียง) |
|---|---|---|---|
| Explore | เริ่มต้น / พ้นภัย / ส่งต่องานเสร็จ | เดินสำรวจปกติ | ไฟขาวนวลกะพริบช้า |
| Approach | เจอเป้าหมายต่อเนื่องเกินเวลาที่กำหนด | เดินช้าลง ค่อยๆ เข้าใกล้ | สีอุ่น ค่อยๆ สว่างขึ้น |
| Interact | ยืนยันเป้าหมายแล้ว (เช่น เจอผู้รอดชีวิต) | หยุดในระยะปลอดภัย ส่งพิกัด สื่อสาร | สว่างขึ้นลงช้าๆ + ข้อความที่อนุมัติแล้ว |
| Escape | hazard (เข้าได้จากทุกสถานะ) | หยุดเกาะพื้น หรือถอยออกจากจุดเสี่ยง | สีส้มนิ่ง + "อยู่นิ่งๆ" (ไม่ใช้แดงกะพริบรัว) |
| LowPower | battery_low (ถ้าไม่ได้อยู่ใน Escape หรือ Interact) | หยุดเดิน ลดการใช้ไฟ ส่งพิกัด | กะพริบหรี่เป็นจังหวะ |

- **State Guard**: แต่ละสถานะกำหนด priority ต่ำสุดที่ยอมให้มาเปลี่ยนสถานะ เช่น Escape รับแค่ระดับความปลอดภัย ระหว่างหนีภัย battery_low จึงดึงออกไปไม่ได้
- **กันสลับรัว** (เช่น ไฟสงบสลับตื่นตระหนก): hysteresis/debounce ที่ต้นทางของเหตุการณ์ + minimum dwell time ในแต่ละสถานะ + เปลี่ยนสีและความสว่างแบบค่อยๆ เปลี่ยน
- **ฮอร์โมนกับ FSM**: FSM กำหนด "โหมด" ส่วนฮอร์โมนกำหนด "ความเข้ม" ภายในโหมด (เช่น Explore แบบระวังมากหรือน้อย)
- **FSM ดีกว่า purely reactive** เพราะสถานะภายในเก็บบริบท สิ่งเร้าเดียวกันให้ผลต่างกันได้ตามสถานการณ์ และพฤติกรรมนิ่งกว่าเพราะต้องผ่านเงื่อนไขก่อนเปลี่ยน
- **adaptation ไม่ใช่ learning**: FSM + AHM ที่กฎตายตัว = state-based adaptation เจอสถานการณ์เดิมก็ตอบแบบเดิม ปิดเปิดเครื่องใหม่ก็เหมือนเดิม การปรับค่าด้วยมือโดยคนก็ไม่ใช่การเรียนรู้ของหุ่น ส่วน robot learning ต้องปรับพารามิเตอร์หรือนโยบายจากประสบการณ์อย่างถาวร และวัดผลได้ว่าดีขึ้น ถ้าจะเพิ่ม learning ต้องจำกัดให้ปรับได้แค่ส่วนที่ไม่ใช่ความปลอดภัย
- **ขอบเขตการสื่อสาร**: ใช้ข้อความชุดที่อนุมัติแล้ว ไม่สั่งให้คนทำสิ่งเสี่ยง ไม่แสดงว่า "ปลอดภัย" ถ้าหุ่นไม่แน่ใจ จำกัดความสว่าง ผู้ควบคุม override ได้ตลอด และบันทึก log ทุกข้อความ

```python
TRANSITIONS = {   # (สถานะปัจจุบัน, เหตุการณ์) -> สถานะใหม่ ; "*" = จากทุกสถานะ
    ("*", "hazard"): "Escape",
    ("Escape", "hazard_clear"): "Explore",
    ("Explore", "target_seen"): "Approach",
    ("Approach", "target_confirmed"): "Interact",
    ("Approach", "target_lost"): "Explore",
    ("Interact", "handoff_done"): "Explore",
    ("Explore", "battery_low"): "LowPower",
    ("Approach", "battery_low"): "LowPower",
    ("LowPower", "charged"): "Explore",
}

GUARD = {         # State Guard: priority ต่ำสุดที่ยอมให้เปลี่ยนสถานะได้
    "Explore": 5, "Approach": 5,
    "Interact": 4,     # ระหว่างสื่อสารกับคน battery_low ต้องรอ
    "Escape": 1,       # ระหว่างหนีภัย รับแค่ระดับความปลอดภัย
    "LowPower": 4,
}


class BehaviorFSM:
    def __init__(self, arbiter, min_dwell, start="Explore", now=0.0):
        self.arbiter, self.min_dwell = arbiter, min_dwell
        self.state, self.since = start, now

    def step(self, events, now):
        for ev in self.arbiter.candidates(events, now, GUARD[self.state]):
            target = TRANSITIONS.get((self.state, ev.kind)) or TRANSITIONS.get(("*", ev.kind))
            if target is None or target == self.state:
                continue
            if ev.priority > 1 and now - self.since < self.min_dwell:
                continue                       # อยู่ไม่ครบเวลาขั้นต่ำ (กันสลับรัว) ยกเว้นเรื่องความปลอดภัย
            self.state, self.since = target, now
            self.arbiter.mark_state_change(now)
            break
        return self.state
```

---

## 11. Actuator Safety Interface

ลำดับ: รับคำสั่ง -> validate (NaN, timestamp) -> angle clamping (soft limit แคบกว่าช่วงเชิงกลจริงเล็กน้อย) -> slew-rate limiting -> จำกัดแรงบิด/กระแส -> driver

- **angle clamping** กันมุมหลุดช่วงเชิงกล ข้อต่อบิดเกิน ชนตัวเอง หรือหนีบสิ่งของ
- **slew-rate limiting** กันคำสั่งกระโดด และหลัง timeout ต้องเริ่มไล่จากมุมจริงที่ encoder อ่านได้ ไม่ใช่จากคำสั่งเก่าที่ค้างอยู่
- **จำกัดแรงบิด/กระแส** ต่อให้ไปโดนอะไร ก็ออกแรงบีบได้ไม่เกินค่าที่ตั้งไว้
- **watchdog** ทุกโมดูลต้อง kick ตามเวลา ไม่งั้นเข้าโหมดปลอดภัย (ชะลอแล้วค้างท่า) แทนการทำตามคำสั่งสุดท้ายไปเรื่อยๆ
- **E-stop** ตัดไฟแบบฮาร์ดแวร์ ไม่ผ่านโปรแกรม ใช้เป็นทางสุดท้าย
- คำสั่งเสียให้ค้างท่า (hold posture) ไม่ตัดไฟทันที เพราะบนพื้นเอียงหรือขรุขระหุ่นจะล้ม
- แต่ละชั้นมีจุดบอด จึงต้องใช้หลายชั้น: clamp ไม่กันการขยับเร็วภายในช่วง, slew-rate ไม่กันการค่อยๆ ไปที่ผิด, watchdog ไม่รู้ว่าค่าที่มาตรงเวลาผิดไหม, E-stop หยุดทุกอย่าง
- trade-off ความเร็วกับความปลอดภัย: ปรับ slew-rate และแรงบิดตามบริบท ใกล้คนหรือสิ่งเปราะบางให้ต่ำ ต้องหลบด่วนให้สูงขึ้นได้แต่ไม่เกินเพดาน

```python
@dataclass
class JointLimits:
    soft_min: float      # แคบกว่าช่วงเชิงกลจริงเล็กน้อย
    soft_max: float
    max_step: float      # slew-rate: เปลี่ยนได้สูงสุดต่อรอบ fast loop
    max_torque: float    # เพดานแรงบิด/กระแส ส่งให้ driver


class ActuatorSafety:
    """ทางเดียวที่คำสั่งจะไปถึงมอเตอร์ (single writer) ; measured ต้องผ่าน validate มาแล้ว"""
    def __init__(self, limits, cmd_timeout):
        self.limits, self.cmd_timeout = limits, cmd_timeout
        self.prev = {}           # คำสั่งรอบก่อนของแต่ละข้อต่อ
        self.resync = set()      # ข้อต่อที่เพิ่งเจอคำสั่งเสียหรือเก่า

    def filter(self, joint, target, cmd_time, measured, now):
        lim = self.limits[joint]
        fresh = (target is not None and math.isfinite(target)
                 and now - cmd_time <= self.cmd_timeout)
        if not fresh:
            self.resync.add(joint)
            target = measured                          # คำสั่งเสีย/เก่า -> ค้างท่าปัจจุบัน ไม่ตัดไฟ
        elif joint in self.resync:
            self.prev[joint] = measured                # กลับมาหลัง timeout: ไล่จากมุมจริง ไม่ใช่คำสั่งเก่า
            self.resync.discard(joint)
        target = min(max(target, lim.soft_min), lim.soft_max)          # angle clamping
        base = self.prev.get(joint, measured)
        step = min(max(target - base, -lim.max_step), lim.max_step)    # slew-rate limiting
        cmd = base + step
        self.prev[joint] = cmd
        return cmd, lim.max_torque


class Watchdog:
    def __init__(self, modules, timeout, now):
        self.timeout = timeout
        self.last = {m: now for m in modules}   # ลงทะเบียนทุกโมดูลตั้งแต่เริ่ม

    def kick(self, module, now):
        self.last[module] = now

    def expired(self, now):
        return [m for m, t in self.last.items() if now - t > self.timeout]
```

---

## 12. Timing และ latency

| โมดูล | loop | อัตราตัวอย่าง |
|---|---|---|
| validate / filter / hysteresis | fast | 100 Hz |
| reflex | fast | 100 Hz |
| CPG + decoder | fast | 50-100 Hz |
| Actuator Safety Interface | fast | 100 Hz ขึ้นไป (หรือใน driver) |
| anomaly detector | slow | 20 Hz |
| AHM | slow | 10 Hz |
| arbiter + FSM | slow | 5-10 Hz |
| ไฟ / เสียง / จอ | slow | 5-10 Hz |

- latency ใน simulation ไม่เท่ากับของจริง simulation วัดแค่เวลาที่ซอฟต์แวร์ส่งคำสั่งออกจากคิว แต่ของจริงต้องรวมการอ่านเซนเซอร์ filter และ debounce (หน่วงไม่เท่ากันแต่ละตัว) การสื่อสาร (CAN/serial) ที่แกว่ง การจัดคิวของ OS และความเฉื่อยของมอเตอร์ เฟือง และแรงต้านของสิ่งแวดล้อม
- ต้องวัดจริงบนฮาร์ดแวร์ตั้งแต่เกิดสิ่งเร้าจนข้อต่อขยับหรือไฟเปลี่ยนจริง ใช้ค่า worst case ไม่ใช่ค่าเฉลี่ย แล้วตั้ง timeout และเกณฑ์จากค่าที่วัดได้พร้อมเผื่อ และทดสอบแบบ hardware-in-the-loop
- fast loop ต้องไม่รอ slow loop ถ้าพารามิเตอร์จาก slow loop เก่าเกินกำหนด ให้ใช้ safe default

---

## 13. Safe fallback (สรุป)

| ปัญหา | ตรวจจับด้วย | การตอบสนอง |
|---|---|---|
| ค่าเซนเซอร์เสีย / ค้าง / timeout | validate | ไม่ใช้ค่านั้น ถ้านานเกินกำหนด -> ชะลอ หยุด ค้างท่า แจ้งเตือน |
| คำสั่งข้อต่อกระโดดหรือเกินช่วง | Actuator Safety | clamp + slew-rate |
| คำสั่งเสียหรือไม่มา | Actuator Safety + watchdog | ค้างท่า |
| ขาตกหลุมหรือชนสิ่งกีดขวาง | closed-loop CPG | หน่วงเฟส / elevator reflex |
| ฮอร์โมนค้างหรือโมดูลหยุดเงียบ | ahm_health + watchdog | safe default + แจ้งเตือน + รีเซ็ต |
| ทุกขาผิดพร้อมกัน / ติดค้าง | anomaly detector (global, stall) | หยุด ค้างท่า ลองกู้ตัวจำนวนครั้งจำกัด แจ้งเตือน |
| actuator ติด กระแสสูงค้าง | กระแส + encoder | ลดแรงบิดหรือหยุดข้อต่อนั้น ไม่หาย -> E-stop |
| slow loop ค้าง | timestamp ของพารามิเตอร์ + watchdog | fast loop ใช้ safe default |
| เหตุการณ์ขัดกัน | arbiter + State Guard | ทำตาม priority สภาวะที่ต่ำกว่ารอไว้ก่อน |
| การสื่อสารกับไฟ/จอขาด | heartbeat | แสดงรูปแบบปลอดภัยของตัวเอง ไม่กระทบการเคลื่อนที่ |
| ควบคุมไม่ได้จริง | คน / ฮาร์ดแวร์ | E-stop |

---

## 14. Checklist ทดสอบก่อนใช้งานจริง

- [ ] ยิง NaN, ค่าขอบ (0, 65535), ค่าค้าง และตัดสายเซนเซอร์ทีละตัว -> ต้องไม่กระชากและเข้า fallback
- [ ] วางวัตถุที่ระยะใกล้เกณฑ์ -> ไม่ chattering
- [ ] ทำให้คำสั่ง timeout แล้วกลับมา -> ข้อต่อไม่กระโดด
- [ ] สั่งมุมเกินช่วง -> โดน clamp
- [ ] ขาตกหลุม / ขาชนสิ่งกีดขวาง -> หน่วงเฟส / elevator reflex ไม่ลากขา
- [ ] สิ่งเร้าสั้นๆ ซ้ำๆ -> ฮอร์โมนไม่ทำให้พฤติกรรมสลับไปมา
- [ ] สิ่งเร้าแรงต่อเนื่องนาน -> H ไม่ชนเพดานจนแยกระดับไม่ได้ และลดลงตามครึ่งชีวิตที่ตั้งไว้
- [ ] หยุด process ของ AHM -> watchdog จับได้ ใช้ safe default และแจ้งเตือน
- [ ] เซนเซอร์ต้นทางค้างค่าสูงสุด -> ไม่ทำให้ H ค้าง
- [ ] ทำให้ทุกขาลื่นหรือติดพร้อมกัน -> ได้ COMMON_MODE หรือ STALL
- [ ] เปลี่ยนท่าเดินระหว่างเดิน -> anomaly detector ไม่แจ้งผิด
- [ ] ยิงเหตุการณ์สองอัตราพร้อมกันในหลายลำดับ -> ไม่มี race condition และ guard ทำงาน
- [ ] วัด latency จริงแบบ worst case ของทุกเส้นทางสำคัญ
- [ ] กด E-stop ตอนซอฟต์แวร์ค้าง -> ตัดไฟได้จริง

---

## 15. บทเรียนจากโจทย์ (ปัญหา -> สาเหตุ -> วิธีแก้)

| ปัญหา | สาเหตุ | วิธีแก้ |
|---|---|---|
| มอเตอร์สั่น (chattering) | single threshold + noise | low-pass filter + hysteresis / debounce |
| ข้อต่อกระชากจนพังเมื่อเจอ NaN หรือค่าขอบ | ไม่ตรวจข้อมูล ไม่มีชั้นกันก่อนมอเตอร์ | validate + Actuator Safety Interface |
| ข้อต่อกระโดดหลัง timeout | ไล่จากคำสั่งเก่า | slew-rate โดยเริ่มจากมุมจริง |
| ไม่รู้ว่าเท้าแตะพื้น / ขาไหนห้อย | ไม่มี proprioception | force/tactile + encoder + IMU |
| ข้อเสนอ "ตัดไฟทันทีเสมอ" | หุ่นจะล้มบนพื้นเอียง | hold posture, E-stop เป็นทางสุดท้าย |
| ขาเคลื่อนพร้อมกัน ไม่เป็น tripod | ส่งสัญญาณเดียวกันทุกขา | แบ่งกลุ่ม + กลับเฟส 180 องศา |
| open-loop CPG ล้มในหลุม / ลากขาที่ชน | ไม่ฟัง feedback | phase resetting + elevator reflex |
| เพิ่มความถี่ตอนปีนลาดแล้วลื่น | ความถี่ไม่เพิ่มแรงหรือระยะยกขา | เพิ่ม amplitude / แรง |
| พฤติกรรมกระชากตามสิ่งเร้าสั้นๆ | direct reactive mapping ไม่มีความจำ | AHM |
| ฮอร์โมนลืมเร็วเกิน | production ต่ำ clearance สูง | จูนตามหัวข้อ 5.2 |
| ฮอร์โมนชนเพดานค้าง ฟื้นช้า | production สูง clearance ต่ำ | soft saturation + clamp ทุกรอบ + จูน |
| ฮอร์โมนไม่มีเพดานจนขากวาดเกิน | ไม่มี bounds และไม่จำกัดผล | bounds + Bounded Modulation Interface |
| เซนเซอร์ค้างค่าสูงสุดทำให้ฮอร์โมนพุ่ง | ไม่ตรวจ input | validate + fault fallback |
| โมดูลฮอร์โมนหยุดเงียบ | ไม่มี heartbeat | watchdog + แจ้งเตือน |
| correlation ไม่เห็นแรงที่ลดลง | gain/offset invariance | เพิ่ม MAE |
| SD ระหว่างขาไม่เห็นความผิดพลาดที่เกิดพร้อมกัน | common-mode failure | Global Inconsistency |
| ขาเดินปกติแต่ตัวไม่ไป | เทียบแค่ระดับข้อต่อ | forward model ระดับลำตัว + IMU Stall Detector |
| แจ้งผิดปกติทุกก้าว ยิ่งเร็วยิ่งแย่ | ไม่มี time alignment | วัดดีเลย์แล้วเลื่อน expected |
| NaN ตัวเดียวทำให้คำนวณไม่ได้ทั้งหน้าต่าง | ไม่กรองก่อนเข้า sliding window | sanitizer + นับเฉพาะค่าดี |
| หารด้วยศูนย์เมื่อสัญญาณแบน | สูตร correlation | ด่าน SD < eps |
| เปลี่ยนท่าเดินแล้วแจ้งผิดปกติ | forward model ใช้ตารางตายตัว | ใช้สำเนาคำสั่งจริงจาก CPG |
| จาก Escape ไป Sleep จนโดนชน | priority เทียบได้แค่ในรอบเดียวกัน | State Guard |
| หลุดจาก Freeze-Grip ระหว่างอาฟเตอร์ช็อก | ไม่มี guard + แรงบิดเปลี่ยนกระชาก | State Guard + slew-rate |
| สถานะหรือไฟสลับรัวใกล้เกณฑ์ | ไม่มี hysteresis ระดับ FSM | hysteresis / debounce + minimum dwell time |
| อ้างว่าหุ่น "เรียนรู้" | สับสน adaptation กับ learning | แยกให้ชัด (หัวข้อ 10) |
| อ้างว่า latency ใน simulation คือของจริง | ไม่ได้วัดบนฮาร์ดแวร์ | วัดจริงแบบ worst case (หัวข้อ 12) |
| race condition ระหว่างโหมดไฟกับ tactile | ไม่มี timestamp, arbiter, single writer | arbiter + State Guard + single writer + slew-rate |
