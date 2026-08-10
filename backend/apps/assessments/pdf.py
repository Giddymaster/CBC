"""Render a report-card dict (from reports.build_report_card) to PDF bytes."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import CompetencyLevel

LEVEL_COLORS = {
    "EE": colors.HexColor("#22543d"),
    "ME": colors.HexColor("#2a4365"),
    "AE": colors.HexColor("#7b341e"),
    "BE": colors.HexColor("#822727"),
}

ASSESSMENT_ORDER = ["CAT1", "CAT2", "RAT", "MIDTERM", "ENDTERM", "FORMATIVE"]


def render_report_card_pdf(data: dict) -> bytes:
    return render_report_cards_pdf([data])


def render_report_cards_pdf(reports: list) -> bytes:
    """One PDF, one learner per page — a class set (or the whole school)
    prints as a single document."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )
    story = []
    for i, data in enumerate(reports):
        if i:
            story.append(PageBreak())
        story.extend(_report_story(data))
    doc.build(story)
    return buffer.getvalue()


def _report_story(data: dict) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SchoolTitle", parent=styles["Title"], fontSize=16, spaceAfter=2)
    subtitle = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=10,
                              textColor=colors.HexColor("#4a5568"), spaceAfter=10)

    learner = data["learner"]
    school = data["school"]
    term_label = f"Term {data['term']}" if data["term"] else "All terms"
    year_label = str(data["year"]) if data["year"] else ""

    story = [
        Paragraph(school["name"], title_style),
        Paragraph(
            f"{school['county']} County — School code {school['code']}<br/>"
            f"CBC Learner Report Card — {term_label} {year_label}",
            subtitle,
        ),
    ]

    info = Table(
        [
            ["Learner", learner["name"], "Admission No", learner["admission_number"]],
            ["UPI", learner["upi"] or "—", "Grade / Stream",
             f"G{learner['grade']} {learner['stream']}".strip()],
            ["Pathway", learner["pathway"] or "—", "", ""],
        ],
        colWidths=[28 * mm, 62 * mm, 32 * mm, 52 * mm],
    )
    info.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
    ]))
    story.extend([info, Spacer(1, 8 * mm)])

    rows = [["Learning Area", "Assessment", "Marks", "%", "Level"]]
    level_cells = []
    for area, kinds in sorted(data["learning_areas"].items()):
        for kind in ASSESSMENT_ORDER:
            if kind not in kinds:
                continue
            s = kinds[kind]
            percent = (s["marks"] / s["max_marks"] * 100) if s["max_marks"] else 0
            level_cells.append((len(rows), s["competency_level"]))
            rows.append([area, kind, f"{s['marks']:g} / {s['max_marks']}", f"{percent:.0f}%",
                         s["competency_level"]])

    if len(rows) == 1:
        rows.append(["No assessment records for this period", "", "", "", ""])

    table = Table(rows, colWidths=[60 * mm, 30 * mm, 32 * mm, 20 * mm, 32 * mm], repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]
    for row_idx, level in level_cells:
        table_style.append(("TEXTCOLOR", (4, row_idx), (4, row_idx),
                            LEVEL_COLORS.get(level, colors.black)))
        table_style.append(("FONTNAME", (4, row_idx), (4, row_idx), "Helvetica-Bold"))
    table.setStyle(TableStyle(table_style))
    story.extend([table, Spacer(1, 8 * mm)])

    legend = " • ".join(f"{code}: {label}" for code, label in CompetencyLevel.choices)
    story.append(Paragraph(f"<b>Competency levels</b> — {legend}", subtitle))

    # The fee note every Kenyan report form carries: what is owed now, and
    # what to bring on opening day.
    fees = data.get("fees") or {}
    if fees.get("billed") not in (None, "0") or fees.get("next_term_fee"):
        fee_rows = [
            ["Fees this term", f"KES {float(fees.get('billed', 0)):,.0f}"],
            ["Paid", f"KES {float(fees.get('paid', 0)):,.0f}"],
            ["Balance", f"KES {float(fees.get('balance', 0)):,.0f}"],
        ]
        if fees.get("next_term_fee"):
            label = f"Term {fees['next_term']} {fees['next_year']} fee"
            fee_rows.append([label, f"KES {float(fees['next_term_fee']):,.0f}"])
            fee_rows.append([
                "Total payable next term",
                f"KES {float(fees['next_term_total_due']):,.0f}",
            ])
        fee_table = Table(fee_rows, colWidths=[70 * mm, 45 * mm])
        fee_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fffbea")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([
            Spacer(1, 4 * mm),
            Paragraph("<b>Fees</b>", subtitle),
            fee_table,
        ])

    return story
