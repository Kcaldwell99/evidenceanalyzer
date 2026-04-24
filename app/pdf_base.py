import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# =========================================================
# BRAND PALETTE
# =========================================================

PURPLE       = colors.HexColor("#5B2D8E")
PURPLE_LIGHT = colors.HexColor("#7B4DB0")
PURPLE_BG    = colors.HexColor("#F3EEF9")
DARK         = colors.HexColor("#1A1A2E")
GREY_LINE    = colors.HexColor("#CCCCCC")
GREY_TEXT    = colors.HexColor("#555555")
WHITE        = colors.white
BLACK        = colors.black


# =========================================================
# STYLE DEFINITIONS
# =========================================================

def build_styles():
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        "CertTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=PURPLE,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    subtitle = ParagraphStyle(
        "CertSubtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=GREY_TEXT,
        spaceAfter=2,
        alignment=TA_LEFT,
    )

    h2 = ParagraphStyle(
        "CertH2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=PURPLE,
        spaceBefore=14,
        spaceAfter=4,
        alignment=TA_LEFT,
    )

    body = ParagraphStyle(
        "CertBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=DARK,
        spaceAfter=4,
        leading=13,
        alignment=TA_LEFT,
    )

    mono = ParagraphStyle(
        "CertMono",
        parent=base["Normal"],
        fontName="Courier",
        fontSize=8,
        textColor=DARK,
        spaceAfter=4,
        leading=12,
        alignment=TA_LEFT,
    )

    disclaimer = ParagraphStyle(
        "CertDisclaimer",
        parent=base["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=GREY_TEXT,
        spaceAfter=4,
        leading=11,
        alignment=TA_LEFT,
    )

    label = ParagraphStyle(
        "CertLabel",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=GREY_TEXT,
        spaceAfter=2,
        alignment=TA_LEFT,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "h2": h2,
        "body": body,
        "mono": mono,
        "disclaimer": disclaimer,
        "label": label,
    }


# =========================================================
# REUSABLE FLOWABLE HELPERS
# =========================================================

def hr(styles):
    return HRFlowable(
        width="100%",
        thickness=0.5,
        color=GREY_LINE,
        spaceAfter=6,
        spaceBefore=6,
    )


def section_spacer():
    return Spacer(1, 0.15 * inch)


def build_metadata_table(rows, col_widths=None):
    """
    rows: list of (label, value) tuples
    Renders a two-column label/value table with alternating row shading.
    """
    if col_widths is None:
        col_widths = [2.0 * inch, 4.5 * inch]

    styles = build_styles()
    table_data = []
    for label, value in rows:
        table_data.append([
            Paragraph(str(label), styles["label"]),
            Paragraph(str(value) if value is not None else "—", styles["body"]),
        ])

    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, PURPLE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.25, GREY_LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_document(output_path, content, title="Evidentix Certificate"):
    """
    Wraps content flowables in a SimpleDocTemplate and builds the PDF.
    Returns the output path.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title,
        author="Evidentix",
    )
    doc.build(content)
    return output_path