"""ข้อมูลที่ "สมอง" (โน้ตบุ๊ก) ส่งให้ "ตัวโคม" (ตอนนี้โคมจำลอง, ต่อไปคือ ESP32)

ตามกฎของ design notes: ฝั่งสมองส่งได้แค่พารามิเตอร์ ห้ามสั่งมุมข้อต่อตรงๆ
ตอนย้ายไป ESP32 จริง แพ็กเก็ตนี้คือสิ่งที่ส่งผ่าน USB serial (มี timestamp + seq)
"""
from dataclasses import dataclass, field

MODES = ("Idle", "Curious", "Engage", "Fear", "Sleep", "Blind", "Peek", "Sick")

# ค่าปลอดภัย: ใช้เมื่อแพ็กเก็ตเก่าเกินกำหนด หรือสมองมี fault (ช้า เบา นิ่ง ไม่ตามใคร)
SAFE_PARAMS = {
    "tempo": 0.5,         # ตัวคูณความเร็วจังหวะ CPG
    "amp": 0.4,           # ตัวคูณขนาดการเคลื่อนไหว
    "lean": 0.0,          # -1 = ถอยหนี, +1 = โน้มเข้าหา
    "gaze_follow": 0.0,   # 0 = ไม่ตามสายตา, 1 = ตามเต็มที่
    "brightness": 0.35,
    "warmth": 1.0,        # ความแข็งแรง: 1 = สีอารมณ์ปกติ, 0 = ป่วย สีซีด
}

PACKET_STALE_S = 0.5      # แพ็กเก็ตเก่ากว่านี้ -> ฝั่งโคมใช้ SAFE_PARAMS


@dataclass
class ControlPacket:
    t: float                                  # เวลาของข้อมูลที่ใช้ตัดสิน (นาฬิกาเดียวกันทุกฝั่ง)
    mode: str                                 # โหมดจาก FSM
    params: dict = field(default_factory=dict)
    gaze: tuple = None                        # (yaw_deg, pitch_deg) ในกรอบกล้อง, None = ไม่มีเป้าหมาย
    seq: int = 0
