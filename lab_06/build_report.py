from __future__ import annotations

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
OUT = ROOT / "results" / "completed"
SEEDS = (41, 42, 43)
CONDITIONS = ("C0", "C1")
COLORS = {"C0": "#c06a22", "C1": "#137d8e"}


def load_runs() -> list[dict]:
    data = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    return data["runs"]


def set_font(run, size: int = 10, bold: bool = False) -> None:
    run.font.name = "TH Sarabun New"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    run.font.size = Pt(size)
    run.bold = bold


def add_text(doc: Document, text: str, center: bool = False) -> None:
    paragraph = doc.add_paragraph()
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(paragraph.add_run(text))


def add_table(doc: Document, headers: list[str], rows: list[list[str]], size: int = 8) -> None:
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
        for cell, value in zip(cells, row):
            cell.text = str(value)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                set_font(run, size)


def fmt(value, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def create_plots(runs: list[dict]) -> tuple[Path, Path]:
    by_key = {(run["condition"], run["seed"]): run for run in runs}
    x = list(range(len(SEEDS)))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.7))
    for offset, condition in enumerate(CONDITIONS):
        selected = [by_key[(condition, seed)] for seed in SEEDS]
        positions = [i + (offset - 0.5) * width for i in x]
        bars = axes[0].bar(positions, [run["state_transition_count"] for run in selected],
                           width=width, label=condition, color=COLORS[condition])
        for bar, run in zip(bars, selected):
            axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                         str(run["state_transition_count"]), ha="center", fontsize=8)
        bars = axes[1].bar(positions, [run["primary_pass_1s_both_count"] for run in selected],
                           width=width, label=condition, color=COLORS[condition])
        for bar, run in zip(bars, selected):
            axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.08,
                         f'{run["primary_pass_1s_both_count"]}/7', ha="center", fontsize=8)
    axes[0].set_title("State transitions")
    axes[0].set_ylabel("Count in 22 s run")
    axes[0].set_ylim(0, 85)
    axes[1].set_title("Primary both-onset ≤1 s")
    axes[1].set_ylabel("Passing sources")
    axes[1].set_ylim(0, 8.5)
    for axis in axes:
        axis.set_xticks(x, [str(seed) for seed in SEEDS])
        axis.set_xlabel("Synthetic seed")
        axis.grid(axis="y", alpha=0.25)
        axis.set_axisbelow(True)
    axes[0].legend()
    fig.tight_layout()
    summary_plot = OUT / "lab06_seed_comparison.png"
    fig.savefig(summary_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)

    seed_runs = {(run["condition"]): run for run in runs if run["seed"] == 41}
    input_ids = ("button_01", "touch_01", "approach_01", "clear_01",
                 "near_01", "clear_02", "button_02")
    fig, axis = plt.subplots(figsize=(8.5, 3.8))
    y = list(range(len(input_ids)))
    for offset, condition in enumerate(CONDITIONS):
        outcomes = {source["input_id"]: source for source in seed_runs[condition]["source_outcomes"]}
        for i, input_id in enumerate(input_ids):
            latency = outcomes[input_id]["both_latency_s"]
            if latency is not None:
                axis.scatter(latency, i + (offset - 0.5) * 0.22, color=COLORS[condition],
                             marker="o", s=48, label=condition if i == 0 else None)
            else:
                axis.scatter(0, i + (offset - 0.5) * 0.22, color=COLORS[condition],
                             marker="x", s=48, label=condition if i == 0 else None)
    axis.axvline(1.0, color="#b34235", linestyle="--", linewidth=1, label="1 s threshold")
    axis.set_yticks(y, input_ids)
    axis.set_xlabel("Source-to-both-onset latency (s); × at zero denotes N/A/missing")
    axis.set_title("Primary input outcomes, paired seed 41")
    axis.grid(axis="x", alpha=0.25)
    axis.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    latency_plot = OUT / "lab06_latency_seed41.png"
    fig.savefig(latency_plot, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return summary_plot, latency_plot


def main() -> None:
    runs = load_runs()
    summary_plot, latency_plot = create_plots(runs)
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.6)
    section.right_margin = Inches(0.6)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "TH Sarabun New"
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "TH Sarabun New")
    doc.styles["Normal"].font.size = Pt(10)
    doc.styles["Normal"].paragraph_format.space_after = Pt(2)
    doc.styles["Heading 1"].font.size = Pt(14)
    doc.styles["Heading 1"].font.color.rgb = RGBColor(22, 125, 141)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("รายงานปฏิบัติการ Lab 06")
    set_font(run, 22, True)
    run.font.color.rgb = RGBColor(22, 125, 141)
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(subtitle.add_run("Lamp Emotion and Interaction"), 15, True)
    add_text(doc, "รายวิชา Bio Inspired Robotics  |  วันที่ทดลอง: 15 พฤศจิกายน 2026  |  กลุ่ม: ______")
    add_text(doc, "สมาชิก: __________________________________________")

    doc.add_heading("1. วัตถุประสงค์และขอบเขต", level=1)
    add_text(doc, "ออกแบบ transition policy สำหรับ 5-state lamp FSM และเปรียบเทียบ C0 raw inputs กับ C1 debounce/hysteresis โดยใช้ paired synthetic seeds 41–43, movement/RGB response, priority handling และ scheduler เดียวกัน แบบจำลองเป็น proposed course model; ไม่มี learning, physical lamp/robot measurement หรือ hardware safety certification.")
    add_text(doc, "Prediction ก่อนรัน: C1 ควรลดการรับรู้ bounce/noise ซ้ำ แต่อาจเพิ่ม recognized latency; คาดว่า touch ขณะ afraid และ fault ขณะ output neutral จะไม่มี output onset ใหม่. วัด all source outcomes และ statuses ไม่เลือกเฉพาะ success.")

    doc.add_heading("2. FSM และ implementation", level=1)
    add_table(doc, ["State", "fault", "near", "clear", "touch", "button/approach", "timeout", "idle"], [
        ["normal", "normal", "afraid", "normal", "happy", "interested", "hold", "sleepy"],
        ["interested", "normal", "afraid", "normal", "happy", "interested", "normal", "hold"],
        ["happy", "normal", "afraid", "normal", "happy", "interested", "normal", "hold"],
        ["afraid", "normal", "afraid", "normal", "hold", "hold", "hold", "hold"],
        ["sleepy", "normal", "afraid", "normal", "happy", "interested", "hold", "hold"],
    ])
    add_text(doc, "Priority: fault > near > clear > touch > button > approach > timeout > idle. near/clear/fault ใช้ guard กลางและ state afraid hold event ที่เหลือ. Implement touch→happy, timeout interested/happy→normal, idle normal→sleepy. Checker ผ่าน 40 transition pairs.")

    doc.add_heading("3. ผล paired runs", level=1)
    rows = []
    for run in runs:
        rows.append([
            f'{run["condition"]}/{run["seed"]}', str(run["external_input_count"]),
            f'{run["external_responded_both_count"]}/10',
            f'{run["external_pass_1s_both_count"]}/10',
            str(run["external_no_both_onset_count"]),
            fmt(run["max_both_latency_s"]), str(run["state_transition_count"]),
        ])
    add_table(doc, ["Run", "Sources", "Both onset", "≤1 s both", "No onset", "Max s", "Transitions"], rows, 8)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(summary_plot), width=Inches(6.2))
    add_text(doc, "รูปที่ 1 จำนวน state transitions และ primary inputs ที่มีทั้ง motion/RGB onset ภายใน 1 s", center=True)
    add_text(doc, "C1 มี primary pass 7/7 ในทั้งสาม seeds (21/21); C0 ได้ 7/7, 6/7, 6/7 (19/21). State transitions ลดจาก C0=67/72/63 เป็น C1=9/10/9. ใน seed 41, approach_01 ถูก recognize ซ้ำ 16 candidates ใน C0 เทียบ 1 ใน C1. ผลสนับสนุนการลด chatter ใน protocol นี้ แต่ source onset totals ต่อ condition ยังต้องอ่านร่วมกับ missing/status และไม่ใช่ independent physical trials.")

    doc.add_heading("4. ตรวจ timing, priority และ N/A", level=1)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(str(latency_plot), width=Inches(5.8))
    add_text(doc, "รูปที่ 2 latency ของ 7 primary source inputs ใน paired seed 41; เครื่องหมาย × แสดง N/A/missing", center=True)
    add_text(doc, "ตัวอย่าง C1 seed 41: button_01 source=1.00 s, recognized/decision=1.10 s, apply/onset=1.14 s; both latency=.14 s. near_01 onset=7.04 s. touch_conflict recognized=7.06 s แต่ถูก afraid guard คงสถานะ (`policy_held`) จึงไม่มี touch onset. invalid_01 และ stale_01 ขณะ neutral เป็น `no_state_change`, latency=N/A ไม่ใช่ 0. Quiet-to-sleepy เกิด idle ที่ 15.00, output onset 15.04; button_02 ที่ 18.00 ทำให้ recovery จาก sleepy.")
    add_text(doc, "Replay จาก inputs_r01.csv ให้ raw_C1_r01.csv และ events_C1_r01.csv SHA-256 ตรงกับ run เดิม. Latency นี้วัดเฉพาะ software model ตั้งแต่ source onset ถึง applied output change; ไม่ใช่ physical LED/motion onset.")

    doc.add_heading("5. สรุปและข้อจำกัด", level=1)
    add_text(doc, "ข้อมูลรองรับว่า C1 filter ลด state transitions และรับมือ input bounce/noise ได้เสถียรกว่าใน synthetic protocol นี้ โดยยังตอบสนองต่อ 7 primary inputs ได้ภายใน 1 s. Negative result คือบาง inputs ไม่มี both onset เพราะ intentional priority/afraid hold หรือ output เป็น neutral อยู่แล้ว; ควรเก็บ status และ N/A ไว้ ไม่แทนเป็น latency ศูนย์.")
    add_text(doc, "ผลไม่ยืนยัน physical response time, ความปลอดภัยหรือความพึงพอใจของผู้ใช้. ต้องเพิ่มการวัดด้วย clock/camera/photodiode ที่สอบเทียบ, uncertainty, actuator tracking, collision/torque limits และ real interaction trials. Controller เป็น fixed-rule FSM ไม่ได้เรียนรู้หรือปรับ parameter.")
    add_text(doc, "ทำซ้ำจาก lab_06: python check_submission.py --contract baseline; python lab06.py --policy student --condition all --repeats 3 --output-dir results\\completed; replay: python lab06.py --policy student --condition C1 --repeats 1 --replay results\\completed\\inputs_r01.csv --output-dir results\\replay. ใช้ Python 3.13.7.")

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("Lab 06 | Lamp Emotion and Interaction  •  "), 8)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    output = ROOT / "Lab06_Report_TH.docx"
    doc.save(output)
    print(f"Created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
