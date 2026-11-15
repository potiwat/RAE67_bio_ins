from __future__ import annotations

import csv
import hashlib
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


def set_font(run, size: int = 12, bold: bool = False) -> None:
    run.font.name = "TH Sarabun New"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    run.font.size = Pt(size)
    run.bold = bold


def add_text(doc: Document, text: str, center: bool = False) -> None:
    paragraph = doc.add_paragraph()
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(paragraph.add_run(text))


def add_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in cell.paragraphs[0].runs:
            set_font(run, 9, True)
            run.font.color.rgb = RGBColor(255, 255, 255)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "167D8D")
        cell._tc.get_or_add_tcPr().append(shading)
    for values in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, values):
            cell.text = str(text)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                set_font(run, 9)


def make_plots(conditions: list[dict], extremes: dict[str, list[dict]]) -> tuple[Path, Path]:
    colors = {"C0": "#667085", "C1": "#137d8e", "C2": "#c06a22", "C3": "#76538e", "C4": "#315f91"}
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4), sharex=True)
    plots = [
        ("h", "Hormone H", "normalized"),
        ("r", "Receptor output R", "normalized"),
        ("phi_rad", "Bounded phi command", "rad"),
        ("stride_half_m", "Bounded stride command", "m"),
    ]
    for axis, (key, title, unit) in zip(axes.flat, plots):
        for condition, rows in conditions.items():
            axis.plot([float(row["time_s"]) for row in rows],
                      [float(row[key]) if row[key] not in ("", "None") else float("nan") for row in rows],
                      label=condition, color=colors[condition], linewidth=1.5)
        axis.axvspan(10, 20, color="#e7f2f3", zorder=0)
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.grid(alpha=0.25)
        axis.set_xlim(0, 30)
    axes[1, 0].set_xlabel("Time (s)")
    axes[1, 1].set_xlabel("Time (s)")
    axes[0, 0].legend(ncol=5, fontsize=8)
    fig.tight_layout()
    comparison_plot = RESULTS / "comparison" / "time_series.png"
    fig.savefig(comparison_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4.2))
    profile_colors = {"zero": "#667085", "one": "#c06a22", "spike": "#137d8e", "fault": "#76538e"}
    for profile, rows in extremes.items():
        axis.plot([float(row["time_s"]) for row in rows], [float(row["h"]) for row in rows],
                  label=profile, color=profile_colors[profile], linewidth=1.7)
    axis.axvspan(10, 20, color="#e7f2f3", zorder=0)
    axis.set(title="Extreme stimulus profiles: hormone state H", xlabel="Time (s)", ylabel="H (normalized)")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    extreme_plot = RESULTS / "comparison" / "extreme_profiles.png"
    fig.savefig(extreme_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return comparison_plot, extreme_plot


def fmt(value, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def main() -> None:
    metrics = json.loads((RESULTS / "comparison" / "metrics.json").read_text(encoding="utf-8"))
    comparison_traces = {
        condition: read_csv(RESULTS / "comparison" / f"{condition}_step.csv")
        for condition in ("C0", "C1", "C2", "C3", "C4")
    }
    extreme_metrics = {}
    extreme_traces = {}
    for profile in ("zero", "one", "spike", "fault"):
        extreme_metrics[profile] = json.loads((RESULTS / profile / "metrics.json").read_text(encoding="utf-8"))[0]
        extreme_traces[profile] = read_csv(RESULTS / profile / f"C1_{profile}.csv")
    comparison_plot, extreme_plot = make_plots(comparison_traces, extreme_traces)
    controller_hash = hashlib.sha256((ROOT / "student_hormone.py").read_bytes()).hexdigest()

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "TH Sarabun New"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    doc.styles["Normal"].font.size = Pt(12)
    doc.styles["Normal"].paragraph_format.space_after = Pt(3)
    doc.styles["Heading 1"].font.size = Pt(16)
    doc.styles["Heading 1"].font.color.rgb = RGBColor(22, 125, 141)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("รายงานปฏิบัติการ Lab 04")
    set_font(run, 24, True)
    run.font.color.rgb = RGBColor(22, 125, 141)
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(subtitle.add_run("Artificial Hormone Mechanism"), 17, True)
    add_text(doc, "รายวิชา Bio Inspired Robotics  |  วันที่ทดลอง: 11 พฤศจิกายน 2026  |  กลุ่ม: ______")
    add_text(doc, "ชื่อ/รหัสสมาชิก: __________________________________________")

    doc.add_heading("1. วัตถุประสงค์และแบบจำลอง", level=1)
    add_text(doc, "ศึกษาความสัมพันธ์จาก stimulus S ไปยัง production, clearance และ binding ของ hormone H จากนั้นแปลง receptor output R เป็นคำสั่ง bounded phi และ stride ตาม Week 03 เปรียบเทียบ direct response (C0) กับ hormone subsystem (C1–C4)")
    add_text(doc, "สมการต้นทางที่เอกสารรายวิชาเชื่อมโยงกับ Homchanthanakul et al. (2019) อธิบาย Hc จากการผลิตและการกำจัด ส่วนสมการที่ใช้คำนวณตัวเลขในแล็บนี้เป็น proposed course model แบบ Euler: P=k_prod S, C=k_clear H_old, B=k_bind R_old, H_new=clamp(H_old+dt(P−C−B),0,1), R_new=clamp((H_new−H_min)/(H_max−H_min),0,1).")
    add_text(doc, "ใช้ dt=0.05 s, duration=30 s, H0=0 และ stimulus step เป็น 0 ใน [0,10), 1 ใน [10,20), แล้วกลับเป็น 0 ใน [20,30). ทุก condition ใช้ contract จาก Lab 03 และ mapping เดียวกัน")
    add_table(doc, ["Condition", "k_prod", "k_clear", "k_bind", "เปลี่ยนจาก C1"], [
        ["C0", "—", "—", "—", "direct R=S; ไม่มี H"],
        ["C1", "0.8", "0.6", "0.2", "baseline"],
        ["C2", "1.2", "0.6", "0.2", "เพิ่ม production"],
        ["C3", "0.8", "0.25", "0.2", "ลด clearance"],
        ["C4", "0.8", "0.6", "0", "ตัด binding"],
    ])

    doc.add_heading("2. การ implement และตรวจสอบ", level=1)
    add_text(doc, "เติม receptor normalization/clamp และ step update โดยใช้ H_old และ R_old ร่วมกันคำนวณ P/C/B ก่อนอัปเดต H เพียงครั้งเดียว จากนั้นคำนวณ receptor จาก H_new หาก stimulus เป็น NaN, infinity หรืออยู่นอก [0,1] ให้ reset H/R เป็น 0, ตั้ง P/C/B/raw เป็น 0 และยก fault flag")
    add_text(doc, "ผล checker ผ่านครบ 13/13 cases รวม receptor bounds, simultaneous old-state update, hormone clamp และ invalid stimulus 4 กรณี")
    add_text(doc, f"SHA-256 ของ student_hormone.py: {controller_hash}")

    doc.add_heading("3. ผล controlled comparison", level=1)
    table_rows = []
    for metric in metrics:
        table_rows.append([
            metric["condition"], fmt(metric["peak_h"]), fmt(metric["auc_h_left"]),
            fmt(metric["latency_s"]), fmt(metric["rise_10_90_s"]), fmt(metric["recovery_s"]),
            fmt(metric["upper_clamp_fraction"], 4), fmt(metric["phi_total_variation_rad"], 4),
        ])
    add_table(doc, ["Cond.", "Peak H", "AUC H", "Latency (s)", "Rise 10–90% (s)", "Recovery (s)", "Upper clamp", "phi TV (rad)"], table_rows)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(comparison_plot), width=Inches(6.7))
    add_text(doc, "รูปที่ 1 การตอบสนองของ H, R และคำสั่ง bounded ในช่วง stimulus-on 10–20 s (พื้นหลังสีอ่อน)", center=True)
    add_text(doc, "C2 มี latency 0.10 s สั้นกว่า C1 ที่ 0.15 s และ AUC สูงขึ้นจาก 9.999644 เป็น 10.672410; C3 มี AUC สูงสุด 11.389145 และ recovery 5.10 s เทียบกับ C1 ที่ 2.85 s (ช้ากว่า 2.25 s). C2, C3 และ C4 มี peak_H=1.0 แต่ AUC/recovery/clamp fraction แตกต่างกัน จึงใช้ peak เพียงค่าเดียวเปรียบเทียบไม่ได้")
    add_text(doc, "C0 ไม่มี hormone state (peak_H/AUC_H เป็น N/A); receptor ติดตาม stimulus โดยตรง แต่เวลา latency ที่บันทึก post-update คือ 0.05 s ตามความละเอียด sampling ไม่ใช่การตอบสนองต่อเนื่องที่ช้ากว่า")

    doc.add_heading("4. Extreme tests และ Week 03 handoff", level=1)
    extreme_table = []
    for profile in ("zero", "one", "spike", "fault"):
        metric = extreme_metrics[profile]
        extreme_table.append([profile, fmt(metric["peak_h"], 4), str(metric["fault_count"]), fmt(metric["phi_total_variation_rad"], 4)])
    add_table(doc, ["Profile", "Peak H", "Fault count", "phi TV (rad)"], extreme_table)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(extreme_plot), width=Inches(6.2))
    add_text(doc, "รูปที่ 2 H สำหรับ zero, one, spike และ fault profile", center=True)
    fault_row = next(row for row in extreme_traces["fault"] if float(row["input_time_s"]) == 15.0)
    next_row = next(row for row in extreme_traces["fault"] if float(row["input_time_s"]) == 15.05)
    add_text(doc, f'Fault ที่ input_time_s=15.00 สร้าง state เวลา 15.05: fault={fault_row["fault"]}, H={fault_row["h"]}, R={fault_row["r"]}; update ถัดไปที่ 15.10 เริ่มสะสมใหม่ H={next_row["h"]}. Spike มี input=1 เพียงหนึ่ง update ที่ 10.00 และ peak_H=0.04.')
    add_text(doc, "Handoff mapping ให้ R=0 → phi=0.200 rad, stride_half=0.055 m และ R=1 → phi=0.400 rad, stride_half=0.065 m ตาม bounds ใน contract")

    doc.add_heading("5. สรุปและข้อจำกัด", level=1)
    add_text(doc, "ข้อมูลสนับสนุนว่าการเพิ่ม production เร่งการเพิ่ม H และการลด clearance rate ทำให้ recovery ช้าลง; เมื่อ H ชน upper bound ค่า peak อาจเหมือนกันแม้ dynamics ต่างกัน จึงควรอ่าน AUC, recovery และ clamp fraction ร่วมด้วย ค่า total variation ที่ต่ำกว่าไม่ใช่หลักฐานว่า gait ดีขึ้น เพราะ Lab04 ยังไม่ได้จำลอง CPG, gait หรือ body motion")
    add_text(doc, "ผลทั้งหมดเป็น proposed course model และ software fallback เท่านั้น ไม่ยืนยัน actuator limits, contact force, hardware safety หรือ robot stability การทดลองต่อใน Week05 ควรเชื่อม receptor output เข้ากับ CPG และเก็บ metric gait โดยคงการควบคุมตัวแปรและขอบเขตของข้อสรุป")
    add_text(doc, "ทำซ้ำจากโฟลเดอร์ lab_04: python check_submission.py --student-file student_hormone.py; python lab04.py --controller-source student --condition all --profile step --contract ..\\lab_03\\results\\week4_bridge\\handoff_contract.json --output-dir results\\comparison; และรัน extreme cases โดยเปลี่ยน --condition C1 --profile เป็น zero, one, spike หรือ fault พร้อม output-dir results\\<profile>. Raw CSV, config และ metrics อยู่ใน results\\comparison และโฟลเดอร์ extreme case แต่ละชุด")
    add_text(doc, "อ้างอิง: Homchanthanakul et al. (2019), DOI: 10.1109/IROS40897.2019.8968580. สมการ Euler, rates และ bounds ในรายงานนี้เป็นค่าของ proposed course model.")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("Lab 04 | Artificial Hormone Mechanism  •  "), 9)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    output = ROOT / "Lab04_Report_TH.docx"
    doc.save(output)
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
