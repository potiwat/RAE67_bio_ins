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
CONDITIONS = ("B0", "B1", "B2", "B3")
CONTACT_CASES = ("matched", "gain-offset", "mixed-delay", "all-inverted", "constant", "fault")
COLORS = {"B0": "#667085", "B1": "#c06a22", "B2": "#137d8e", "B3": "#76538e"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def set_font(run, size: int = 11, bold: bool = False) -> None:
    run.font.name = "TH Sarabun New"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    run.font.size = Pt(size)
    run.bold = bold


def add_text(doc: Document, text: str, center: bool = False) -> None:
    paragraph = doc.add_paragraph()
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(paragraph.add_run(text))


def add_table(doc: Document, headers: list[str], rows: list[list[str]], size: int = 9) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in cell.paragraphs[0].runs:
            set_font(run, size, True)
            run.font.color.rgb = RGBColor(255, 255, 255)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "167D8D")
        cell._tc.get_or_add_tcPr().append(shading)
    for row in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = str(text)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                set_font(run, size)


def fmt(value, digits: int = 4) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def create_plots() -> tuple[Path, Path]:
    comparison = RESULTS / "comparison"
    interval_rows = {
        condition: load_csv(comparison / f"{condition}_intervals.csv")
        for condition in CONDITIONS
    }
    state_rows = {
        condition: load_csv(comparison / f"{condition}_states.csv")
        for condition in CONDITIONS
    }

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.2), sharex=True)
    series = [
        ("r_used", "R used by controller", "normalized", interval_rows, "command_time_s"),
        ("phi_rad", "Phase command", "rad", interval_rows, "command_time_s"),
        ("stride_half_m", "Stride command", "m", interval_rows, "command_time_s"),
        ("body_x_m", "Body displacement", "m", state_rows, "state_time_s"),
    ]
    for axis, (key, title, unit, rows_by_condition, time_key) in zip(axes.flat, series):
        for condition in CONDITIONS:
            rows = rows_by_condition[condition]
            values = [float(row[key]) if row[key] not in ("", "None") else float("nan") for row in rows]
            axis.plot([float(row[time_key]) for row in rows], values,
                      label=condition, color=COLORS[condition], linewidth=1.35)
        axis.axvspan(10, 20, color="#e7f2f3", zorder=0)
        axis.axvline(15, color="#b34235", linestyle=":", linewidth=1, alpha=0.7)
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.set_xlim(0, 30)
        axis.grid(alpha=0.25)
    axes[1, 0].set_xlabel("Time (s)")
    axes[1, 1].set_xlabel("Time (s)")
    axes[0, 0].legend(ncol=4, fontsize=8)
    fig.tight_layout()
    main_plot = comparison / "lab05_comparison.png"
    fig.savefig(main_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)

    contact = load_json(RESULTS / "contact" / "metrics.json")
    labels = list(CONTACT_CASES)
    mean_sif = [contact[name]["mean_sif"] for name in labels]
    mae = [contact[name]["mean_absolute_error"] for name in labels]
    x = list(range(len(labels)))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].bar(x, [0 if value is None else value for value in mean_sif],
                color=["#137d8e" if value is not None else "#d7dce0" for value in mean_sif])
    axes[0].set_title("Mean valid SIF")
    axes[0].set_ylabel("population SD")
    axes[0].set_ylim(-0.02, 0.62)
    axes[1].bar(x, mae, color="#c06a22")
    axes[1].set_title("Mean absolute error")
    axes[1].set_ylabel("normalized signal")
    for axis in axes:
        axis.set_xticks(x, labels, rotation=25, ha="right")
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
    for index, value in enumerate(mean_sif):
        axes[0].text(index, (0 if value is None else value) + 0.015,
                     "N/A" if value is None else f"{value:.2f}", ha="center", fontsize=8)
    fig.tight_layout()
    contact_plot = RESULTS / "contact" / "contact_metrics.png"
    fig.savefig(contact_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return main_plot, contact_plot


def main() -> None:
    main_metrics = load_json(RESULTS / "comparison" / "metrics.json")
    phi_metrics = load_json(RESULTS / "phi_only" / "metrics.json")
    stride_metrics = load_json(RESULTS / "stride_only" / "metrics.json")
    fault_metrics = load_json(RESULTS / "fault" / "metrics.json")
    contact_metrics = load_json(RESULTS / "contact" / "metrics.json")
    contact_plot = create_plots()[1]
    main_plot = RESULTS / "comparison" / "lab05_comparison.png"
    intervals = load_csv(RESULTS / "comparison" / "B2_intervals.csv")
    fault_intervals = load_csv(RESULTS / "fault" / "B2_intervals.csv")

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "TH Sarabun New"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    doc.styles["Normal"].font.size = Pt(11)
    doc.styles["Normal"].paragraph_format.space_after = Pt(2)
    doc.styles["Heading 1"].font.size = Pt(15)
    doc.styles["Heading 1"].font.color.rgb = RGBColor(22, 125, 141)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("รายงานปฏิบัติการ Lab 05")
    set_font(run, 23, True)
    run.font.color.rgb = RGBColor(22, 125, 141)
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(subtitle.add_run("Hormone → SO(2) CPG → Kinematic Walking"), 16, True)
    add_text(doc, "รายวิชา Bio Inspired Robotics  |  วันที่ทดลอง: 15 พฤศจิกายน 2026  |  กลุ่ม: ______")
    add_text(doc, "ชื่อ/รหัสสมาชิก: __________________________________________")

    doc.add_heading("1. วัตถุประสงค์และขอบเขต", level=1)
    add_text(doc, "เชื่อม hormone controller จาก Week 04 เข้ากับ SO(2) CPG และ kinematic tripod model แล้วเปรียบเทียบ B0 fixed, B1 direct, B2 hormone และ B3 binding ablation ภายใต้ stimulus schedule เดียวกัน ตรวจ timing convention, การเปลี่ยนหนึ่งปัจจัย, software fault fallback และ synthetic predicted–actual contact signals.")
    add_text(doc, "แบบจำลองทั้งหมดเป็น proposed course model: dt=0.05 s, alpha=1.10, warmup CPG 10 s, stimulus 0 ใน [0,10), 1 ใน [10,20), กลับ 0 ใน [20,30). รัน deterministic; repeated runs ไม่ใช่ independent trials.")
    add_text(doc, "Provenance: ใช้ architecture/แนวคิดจาก Ngamkajornwiwat et al. (2020), DOI 10.1109/ACCESS.2020.2992794; hormone Euler P−C−B, mapping, scheduled input และ kinematic body เป็น course model. Contact Pearson เป็น proposed course definition ไม่ใช่การ implement Eq.(3) ตามพิมพ์. Paper Stability/Harmony/Displacement และ physical energy ยังวัดไม่ได้.")
    add_table(doc, ["Condition", "R ที่ใช้", "k_prod", "k_clear", "k_bind"], [
        ["B0", "fixed 0", "—", "—", "—"],
        ["B1", "direct S", "—", "—", "—"],
        ["B2", "H(t_k)", "0.8", "0.6", "0.2"],
        ["B3", "H(t_k)", "0.8", "0.6", "0"],
    ])

    doc.add_heading("2. Comparison และ timing", level=1)
    summary_rows = []
    for condition in CONDITIONS:
        metric = main_metrics[condition]
        on = metric["segments"]["on"]
        summary_rows.append([
            condition, fmt(metric["phi_total_variation_rad"], 6), fmt(metric["phi_max_step_rad"], 4),
            fmt(metric["stride_total_variation_m"], 6), fmt(metric["command_latency_s"], 3),
            fmt(metric["command_recovery_s"], 3), fmt(on["frequency_hz"], 4),
            fmt(on["distance_m"], 4),
        ])
    add_table(doc, ["Cond.", "TV phi", "Max Δphi", "TV stride", "Cmd latency", "Recovery", "On freq. (Hz)", "On dist. (m)"], summary_rows, 8)
    add_text(doc, "B2 timing check (input/command time → state end): t=10.00: H 0→0.04, R_used=0, phi=.200 rad, stride=.055 m; t=10.05: H .04→.0784, R_used=.04, phi=.208 rad, stride=.0554 m; t=20.00: H .999715→.959727, R_used=.999715, phi≈.399943 rad, stride≈.064997 m.")
    add_text(doc, "B1 ใช้ S_k แบบ direct ใน command เวลา 10.00 ทำให้ command latency=0; state CSV บันทึก post-update จึง state latency=.05 s จาก sampling. ทุก condition ใช้ warmup CPG เดียวกันและ reset H/R, body origin, foot anchors และ log ก่อนเริ่ม trial.")
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(main_plot), width=Inches(6.6))
    add_text(doc, "รูปที่ 1 สัญญาณ R_used, phi, stride และ body displacement; แถบสีเขียวคือช่วง stimulus-on และเส้นประคือ fault time 15 s", center=True)

    doc.add_heading("3. ผลและการวิเคราะห์", level=1)
    add_text(doc, "B1 direct มี on frequency 1.2684 Hz และ on distance 1.8252 m เทียบ B0 fixed ที่ .6249 Hz และ .7787 m. B2 hormone มี 1.2028 Hz และ 1.7063 m; B3 binding ablation มี 1.2258 Hz และ 1.7275 m. ผลเหล่านี้เป็น motion ใน kinematic model ตาม scheduled stimulus ไม่ได้แปลว่าการเดินจริงดีขึ้น.")
    add_text(doc, "B2 command latency=.15 s และ recovery=2.85 s เทียบ B1 ที่ 0/.00 s; max Δphi ต่อ step ของ B2=.008 rad เทียบ B1=.20 rad. อย่างไรก็ตาม total variation ใกล้กัน (.399827 เทียบ .400000 rad), เพราะ TV รวมการเปลี่ยนตลอดการขึ้นและลง ไม่ใช่ตัวชี้วัด smoothness เฉพาะจุด. B3 คง hormone memory แต่ตัด binding; มี recovery 3.80 s และ AUC_H=10.754720 normalized H·s เทียบ B2 9.999644.")
    add_text(doc, "Bounds เดียวกันไม่ได้บังคับ trajectory ให้เท่ากัน: B1 กระโดดตรงไป phi=.40 rad ส่วน B2 ค่อย ๆ เพิ่มและลด. Segment frequency pre/on/off ช่วยแยก transient; ค่าเฉลี่ย 30 s จะรวมช่วงเหล่านี้และซ่อนผลของเวลา.")

    doc.add_heading("4. One-factor และ fault", level=1)
    add_table(doc, ["Mapping", "Condition", "On frequency (Hz)", "On distance (m)", "TV phi (rad)", "TV stride (m)"], [
        ["phi-only", "B1", fmt(phi_metrics["B1"]["segments"]["on"]["frequency_hz"]), fmt(phi_metrics["B1"]["segments"]["on"]["distance_m"]), fmt(phi_metrics["B1"]["phi_total_variation_rad"]), fmt(phi_metrics["B1"]["stride_total_variation_m"])],
        ["phi-only", "B2", fmt(phi_metrics["B2"]["segments"]["on"]["frequency_hz"]), fmt(phi_metrics["B2"]["segments"]["on"]["distance_m"]), fmt(phi_metrics["B2"]["phi_total_variation_rad"]), fmt(phi_metrics["B2"]["stride_total_variation_m"])],
        ["stride-only", "B1", fmt(stride_metrics["B1"]["segments"]["on"]["frequency_hz"]), fmt(stride_metrics["B1"]["segments"]["on"]["distance_m"]), fmt(stride_metrics["B1"]["phi_total_variation_rad"]), fmt(stride_metrics["B1"]["stride_total_variation_m"])],
        ["stride-only", "B2", fmt(stride_metrics["B2"]["segments"]["on"]["frequency_hz"]), fmt(stride_metrics["B2"]["segments"]["on"]["distance_m"]), fmt(stride_metrics["B2"]["phi_total_variation_rad"]), fmt(stride_metrics["B2"]["stride_total_variation_m"])],
    ])
    fault_at = next(row for row in fault_intervals if float(row["command_time_s"]) == 15.0)
    fault_next = next(row for row in fault_intervals if float(row["command_time_s"]) == 15.05)
    add_text(doc, f'Fault fallback ทำก่อน command ของ interval [15.00,15.05): B2 fault={fault_at["fault"]}, H_used/R_used=0/0, phi=.200 rad, stride=.055 m และ state H ที่ 15.05={fault_at["h_state_end"]}; interval ถัดไป command 15.05 สะสม H ถึง {fault_next["h_state_end"]} ที่ state 15.10. นี่เป็น software fallback ไม่ใช่ hardware safety/stop guarantee.')
    add_text(doc, "ใน phi-only, stride คง .055 m และ B2 on frequency/distance ต่ำกว่า B1 เล็กน้อย (1.2028 Hz/1.4672 m เทียบ 1.2684 Hz/1.5491 m). ใน stride-only, phi คง .20 rad; B2 on distance=.9017 m เทียบ B1=.9147 m ขณะที่ frequency เท่ากัน .6249 Hz. ผลนี้แยกผลของ parameter ตาม model แต่ยังไม่ใช่ causal claim ต่อ robot จริง.")

    doc.add_heading("5. Contact mini-lab (synthetic)", level=1)
    contact_rows = []
    for case in CONTACT_CASES:
        metric = contact_metrics[case]
        sif = metric["mean_sif"]
        si_lf = metric["mean_si"]["LF"]
        contact_rows.append([
            case, fmt(si_lf, 4), fmt(sif, 4), fmt(metric["mean_absolute_error"], 4),
            str(metric["valid_sif_rows"]),
        ])
    add_table(doc, ["Case", "Mean SI LF", "Mean SIF", "Mean abs. error", "Valid SIF rows"], contact_rows, 8)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(contact_plot), width=Inches(6.3))
    add_text(doc, "รูปที่ 2 ค่า SIF และ absolute error จาก synthetic signal cases", center=True)
    add_text(doc, "Gain-offset มี SI≈1 และ SIF≈0 แต่ MAE=.1628; all-inverted มี SI≈−1 ทุกขา จึง SIF≈0 แม้ error สูง. Constant variance=0 จึง SI/SIF=N/A. Mixed-delay ให้ mean SIF≈.5000. Fault sample หนึ่งทำให้ 50 rolling windows เพิ่มเติมของ LF invalid; รวม startup 49 rows แล้ว unavailable SIF=99 rows. Release ที่ SIF=0 คือ .5 ตามสมการที่เลือก; ไม่มี Cg/HR/MI_H recurrence ใน demo.")

    doc.add_heading("6. ข้อสรุปและขอบเขต", level=1)
    add_text(doc, "หลักฐานรองรับว่า direct path เปลี่ยน command ทันที ขณะที่ hormone path มี latency, gradual command steps และ recovery; binding ablation เปลี่ยน recovery/AUC ใน course model. หลักฐานยังไม่รองรับความมั่นคง การใช้พลังงาน การตอบสนองต่อ terrain จริง หรือผลสำเร็จของ ALCS/MNLC เพราะไม่มี closed-loop terrain, contact force, robot dynamics, actuator measurements และ independent trials.")
    add_text(doc, "คำสั่งทำซ้ำจาก lab_05: python lab05.py --condition all --profile step --mapping both --output-dir results\\comparison; python lab05.py --mapping phi-only --output-dir results\\phi_only; python lab05.py --mapping stride-only --output-dir results\\stride_only; python lab05.py --condition all --profile fault --output-dir results\\fault; python contact_demo.py --output-dir results\\contact. Zero/one/spike run ด้วย --condition B2 --profile <profile> และ output-dir results\\<profile>. Raw CSV, config, metrics, source_snapshot และ manifest อยู่ในแต่ละ output folder.")
    add_text(doc, "อ้างอิง: Ngamkajornwiwat et al. (2020), IEEE Access, DOI 10.1109/ACCESS.2020.2992794; model definitions และ provenance ดู SOURCES.md. ตัวเลขรายงานนี้เป็นผล simulation ของ proposed course model เท่านั้น.")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("Lab 05 | Hormone → SO(2) CPG  •  "), 9)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    output = ROOT / "Lab05_Report_TH.docx"
    doc.save(output)
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
