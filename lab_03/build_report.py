from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def set_font(run, size: int = 13, bold: bool = False) -> None:
    run.font.name = "TH Sarabun New"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    run.font.size = Pt(size)
    run.bold = bold


def add_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            set_font(run, 10, True)
            run.font.color.rgb = RGBColor(255, 255, 255)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "167D8D")
        cell._tc.get_or_add_tcPr().append(shading)
    for values in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, values):
            cell.text = text
            for run in cell.paragraphs[0].runs:
                set_font(run, 10)


def add_text(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(text)
    set_font(run)


def make_plots(conditions: list[dict[str, str]], bridge_rows: list[dict[str, str]]) -> tuple[Path, Path]:
    labels = [row["condition"].replace("_", " ") for row in conditions]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
    metrics = [
        ("mean_speed_m_s", "Mean speed", "m/s", 1, "#167d8d"),
        ("oscillation_frequency_hz", "Oscillation frequency", "Hz", 1, "#e07a5f"),
        ("maximum_foot_clearance_m", "Maximum foot clearance", "mm", 1000, "#6a8caf"),
    ]
    for axis, (key, title, unit, scale, color) in zip(axes, metrics):
        values = [float(row[key]) * scale for row in conditions]
        bars = axis.bar(labels, values, color=color)
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
        axis.tick_params(axis="x", labelrotation=15)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                      f"{value:.3f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    comparison = RESULTS / "gait_comparison" / "comparison_metrics.png"
    fig.savefig(comparison, dpi=180, bbox_inches="tight")
    plt.close(fig)

    times = [float(row["time_s"]) for row in bridge_rows]
    phi = [float(row["phi_rad"]) for row in bridge_rows]
    stride = [float(row["stride_half_m"]) for row in bridge_rows]
    body_x = [float(row["body_x_m"]) for row in bridge_rows]
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 5.2), sharex=True)
    axes[0].plot(times, phi, color="#167d8d")
    axes[0].set_ylabel("phi (rad)")
    axes[0].set_title("Week 4 handoff: bounded parameter commands")
    axes[0].grid(alpha=0.25)
    stride_axis = axes[0].twinx()
    stride_axis.plot(times, stride, color="#e07a5f")
    stride_axis.set_ylabel("stride_half (m)")
    axes[1].plot(times, body_x, color="#6a8caf")
    axes[1].set_ylabel("Body displacement (m)")
    axes[1].set_xlabel("Time (s)")
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    handoff = RESULTS / "week4_bridge" / "week4_bridge_plot.png"
    fig.savefig(handoff, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return comparison, handoff


def main() -> None:
    conditions = read_csv(RESULTS / "gait_comparison" / "conditions_summary.csv")
    bridge_rows = read_csv(RESULTS / "week4_bridge" / "week4_bridge.csv")
    with (RESULTS / "week4_bridge" / "handoff_contract.json").open(encoding="utf-8") as file:
        bridge_contract = json.load(file)
    comparison_plot, handoff_plot = make_plots(conditions, bridge_rows)

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "TH Sarabun New"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    doc.styles["Normal"].font.size = Pt(13)
    doc.styles["Heading 1"].font.size = Pt(18)
    doc.styles["Heading 1"].font.color.rgb = RGBColor(22, 125, 141)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("รายงานปฏิบัติการ Lab 03")
    set_font(run, 26, True)
    run.font.color.rgb = RGBColor(22, 125, 141)
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(subtitle.add_run("SO(2) CPG และการเดินแบบ Alternating Tripod ของหุ่นยนต์หกขา"), 18, True)
    add_text(doc, "รายวิชา Bio Inspired Robotics  |  วันที่ทดลอง: 11 พฤศจิกายน 2026  |  กลุ่ม: 1")
    add_text(doc, "สมาชิก: __________________________________________")

    doc.add_heading("1. วัตถุประสงค์", level=1)
    add_text(doc, "ศึกษาวงจร Central Pattern Generator (CPG) แบบ SO(2) การถอดรหัสสัญญาณเป็นการเดินแบบ alternating tripod และ bounded mapping จากสัญญาณ modulation m(t) ไปปรับ phase increment (phi) และ stride")
    doc.add_heading("2. วิธีการทดลองและการตั้งค่า", level=1)
    add_text(doc, "เติมฟังก์ชัน so2_step, decode_tripod และ bounded_modulation ใน student_cpg.py ตรวจด้วย grader และรัน gait comparison โดยใช้ dt = 0.05 s ระยะทดลอง 30 s และ warmup 10 s")
    add_table(doc, ["Condition", "alpha", "phi (rad)", "ตัวแปรที่เปลี่ยน"], [
        ["baseline", "1.10", "0.20", "จุดอ้างอิง"],
        ["fast", "1.10", "0.40", "เพิ่ม phi เท่านั้น"],
        ["high_gain", "1.30", "0.20", "เพิ่ม alpha เท่านั้น"],
    ])
    add_text(doc, "อัปเดต o1 และ o2 พร้อมกันจากค่าในเวลาปัจจุบัน แล้วผ่าน tanh โดยไม่ใช้เอาต์พุตใหม่ของ o1 ไปคำนวณ o2 ในรอบเดียวกัน")

    doc.add_heading("3. ผลการตรวจโปรแกรม", level=1)
    add_text(doc, "ผล grader ผ่าน 5 จาก 5 checks ครอบคลุมสมการ SO(2), simultaneous update, tripod decoder และ bounded mapping รายละเอียดอยู่ใน results/my_grade.json")
    doc.add_heading("4. ผล gait comparison", level=1)
    rows = []
    for row in conditions:
        rows.append([
            row["condition"], f'{float(row["mean_speed_m_s"]):.6f}',
            f'{float(row["oscillation_frequency_hz"]):.6f}',
            f'{float(row["duty_factor_LF"]):.6f}', row["minimum_support_legs"],
            f'{float(row["maximum_foot_clearance_m"]) * 1000:.3f}',
        ])
    add_table(doc, ["Condition", "Speed (m/s)", "Frequency (Hz)", "Duty factor LF", "Min support", "Clearance (mm)"], rows)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(comparison_plot), width=Inches(6.7))
    caption = doc.add_paragraph("รูปที่ 1 เปรียบเทียบความเร็ว ความถี่การแกว่ง และระยะยกเท้าสูงสุด")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading("5. วิเคราะห์ผล", level=1)
    add_text(doc, "เมื่อเพิ่ม phi จาก 0.20 เป็น 0.40 rad โดยคง alpha เท่าเดิม ความเร็วเพิ่มจาก 0.077756 เป็น 0.155511 m/s และความถี่เพิ่มจาก 0.625000 เป็น 1.267123 Hz ใกล้เคียงสองเท่า")
    add_text(doc, "เมื่อเพิ่ม alpha จาก 1.10 เป็น 1.30 clearance สูงสุดเพิ่มจาก 17.095 เป็น 24.637 mm ขณะที่ความถี่ลดจาก 0.625000 เป็น 0.544218 Hz ความเร็วเพิ่มเป็น 0.094457 m/s แสดงว่า metric ต่าง ๆ ไม่จำเป็นต้องเปลี่ยนไปในทิศทางเดียวกัน")
    add_text(doc, "Duty factor ของขา LF อยู่ประมาณ 0.494–0.501 และ minimum support เท่ากับ 3 ขาในทุก condition ตามโครงสร้าง alternating tripod decoder")

    doc.add_heading("6. Week 4 handoff", level=1)
    segment_rows = []
    for segment in bridge_contract["segments"]:
        segment_rows.append([
            f'{segment["start_s"]}–{segment["end_s"]} s',
            f'{float(segment["modulator_m"]):.1f}', f'{float(segment["phi_rad"]):.3f}',
            f'{float(segment["stride_half_m"]):.3f}',
            f'{float(segment["mean_speed_m_s"]):.6f}',
            f'{float(segment["frequency_hz"]):.6f}',
        ])
    add_table(doc, ["ช่วงเวลา", "m(t)", "phi (rad)", "stride_half (m)", "Speed (m/s)", "Frequency (Hz)"], segment_rows)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(handoff_plot), width=Inches(6.5))
    caption = doc.add_paragraph("รูปที่ 2 คำสั่ง phi และ stride แบบ bounded พร้อมตำแหน่งลำตัว")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(doc, "การกำหนด bounds จำกัด phi ในช่วง 0.10–0.45 rad และ stride_half ในช่วง 0.040–0.070 m ใน Week 4 สามารถใช้ hormone/receptor signal แทน m(t) ได้ โดยคาดว่าจะเห็น lag จากพลวัตการเพิ่มและสลายของ hormone")

    doc.add_heading("7. ข้อจำกัดของแบบจำลอง", level=1)
    add_text(doc, "นี่คือ kinematic teaching model สำหรับตรวจ timing, phase, foot placement และ metric pipeline ไม่ได้จำลอง contact force, friction, motor torque, rigid-body dynamics หรือ dynamic stability จึงไม่ยืนยันสมรรถนะของหุ่นยนต์จริง")
    doc.add_heading("8. สรุป", level=1)
    add_text(doc, "การเพิ่ม phi ทำให้ cadence และความเร็วเพิ่มชัดเจนในแบบจำลอง ส่วน alpha ที่สูงขึ้นเพิ่ม clearance และเปลี่ยนความถี่ที่วัดได้ decoder รักษา minimum support ไว้ 3 ขา และ bounded mapping สร้าง handoff interface สำหรับ Week 4 ตามช่วงที่กำหนด")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("Lab 03 | SO(2) CPG  •  หน้า "), 10)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    output = ROOT / "Lab03_Report_TH.docx"
    doc.save(output)
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
