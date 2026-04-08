# Evidentix comparison PDF v2 — rebuilt 2026-04-08
import os
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import Flowable


# ── Brand colors ──────────────────────────────────────────────────────────────
PURPLE       = colors.HexColor("#5B2D8E")
PURPLE_LIGHT = colors.HexColor("#7B4DB8")
PURPLE_BG    = colors.HexColor("#F3EEFF")
DARK         = colors.HexColor("#1A1A2E")
GREY_LINE    = colors.HexColor("#D8D0E8")
GREY_TEXT    = colors.HexColor("#555555")
WHITE        = colors.white

VERDICT_COLORS = {
    "exact":    (colors.HexColor("#1A6B2E"), colors.HexColor("#E6F4EA")),  # green
    "high":     (colors.HexColor("#1A4D8F"), colors.HexColor("#E8F0FB")),  # blue
    "probable": (colors.HexColor("#7A5100"), colors.HexColor("#FFF8E1")),  # amber
    "inconc":   (colors.HexColor("#8F3800"), colors.HexColor("#FFF3E0")),  # orange
    "no":       (colors.HexColor("#8B0000"), colors.HexColor("#FFEBEE")),  # red
}


def _verdict_colors(confidence_level: str):
    cl = (confidence_level or "").lower()
    if "exact" in cl:
        return VERDICT_COLORS["exact"]
    if "high" in cl:
        return VERDICT_COLORS["high"]
    if "probable" in cl:
        return VERDICT_COLORS["probable"]
    if "inconclusive" in cl:
        return VERDICT_COLORS["inconc"]
    return VERDICT_COLORS["no"]


# ── Custom flowables ───────────────────────────────────────────────────────────

class HeaderBanner(Flowable):
    """Full-width purple header with title and subtitle."""
    def __init__(self, title, subtitle, width):
        Flowable.__init__(self)
        self.banner_title = title
        self.subtitle = subtitle
        self.banner_width = width
        self.height = 80

    def draw(self):
        c = self.canv
        # Background
        c.setFillColor(PURPLE)
        c.rect(0, 0, self.banner_width, self.height, fill=1, stroke=0)
        # Title
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(24, 48, self.banner_title)
        # Subtitle
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#D8C8F8"))
        c.drawString(24, 30, self.subtitle)
        # Bottom accent line
        c.setFillColor(PURPLE_LIGHT)
        c.rect(0, 0, self.banner_width, 4, fill=1, stroke=0)


class VerdictBox(Flowable):
    """Color-coded verdict badge."""
    def __init__(self, confidence_level, conclusion_title, width):
        Flowable.__init__(self)
        self.confidence_level = confidence_level
        self.conclusion_title = conclusion_title
        self.box_width = width
        self.height = 52

    def draw(self):
        text_color, bg_color = _verdict_colors(self.confidence_level)
        c = self.canv
        # Background
        c.setFillColor(bg_color)
        c.roundRect(0, 0, self.box_width, self.height, 6, fill=1, stroke=0)
        # Left accent bar
        c.setFillColor(text_color)
        c.rect(0, 0, 5, self.height, fill=1, stroke=0)
        # Label
        c.setFont("Helvetica", 8)
        c.setFillColor(GREY_TEXT)
        c.drawString(16, 36, "FORENSIC VERDICT")
        # Title
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(text_color)
        c.drawString(16, 14, self.conclusion_title)


class SectionHeading(Flowable):
    """Purple-accented section heading with horizontal rule."""
    def __init__(self, number, title, width):
        Flowable.__init__(self)
        self.number = number
        self.heading_title = title
        self.heading_width = width
        self.height = 26

    def draw(self):
        c = self.canv
        # Left accent
        c.setFillColor(PURPLE)
        c.rect(0, 4, 3, 18, fill=1, stroke=0)
        # Number badge
        c.setFillColor(PURPLE_BG)
        c.roundRect(8, 4, 22, 18, 3, fill=1, stroke=0)
        c.setFillColor(PURPLE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(19, 9, str(self.number))
        # Title
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(DARK)
        c.drawString(38, 8, self.heading_title)
        # Rule
        c.setStrokeColor(GREY_LINE)
        c.setLineWidth(0.5)
        c.line(0, 2, self.heading_width, 2)


# ── Style helpers ──────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "EvBody", parent=base["Normal"],
        fontSize=9.5, leading=14,
        textColor=DARK, spaceAfter=4,
    )
    small = ParagraphStyle(
        "EvSmall", parent=body,
        fontSize=8.5, textColor=GREY_TEXT,
    )
    label = ParagraphStyle(
        "EvLabel", parent=body,
        fontSize=8, textColor=GREY_TEXT,
        spaceBefore=0, spaceAfter=0,
    )
    mono = ParagraphStyle(
        "EvMono", parent=body,
        fontName="Courier", fontSize=7.5,
        textColor=GREY_TEXT,
    )
    footer = ParagraphStyle(
        "EvFooter", parent=base["Normal"],
        fontSize=7.5, textColor=GREY_TEXT,
        alignment=TA_CENTER,
    )
    return body, small, label, mono, footer


def _metric_table(rows, col_widths, zebra=True):
    """Build a styled two-column metric table."""
    style = [
        ("FONTNAME",  (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("FONTNAME",  (0, 0), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1),  DARK),
        ("TEXTCOLOR", (1, 0), (1, -1),  GREY_TEXT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("GRID",      (0, 0), (-1, -1), 0.25, GREY_LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.white, colors.HexColor("#FAF8FF")] if zebra else [colors.white]),
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle(style))
    return t


def _diff_table(differences, col_widths):
    if not differences:
        return None
    rows = [["Field / Note", "Original → Suspect"]]
    for d in differences:
        if isinstance(d, dict):
            field = d.get("field", "")
            orig  = str(d.get("original", "—"))
            susp  = str(d.get("suspect", "—"))
            rows.append([field, f"{orig}  →  {susp}"])
        else:
            rows.append(["", str(d)])

    style = [
        ("BACKGROUND",   (0, 0), (-1, 0),  PURPLE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",         (0, 0), (-1, -1), 0.25, GREY_LINE),
        ("ROWBACKGROUNDS",(0, 1),(-1, -1), [colors.white, colors.HexColor("#FAF8FF")]),
        ("FONTNAME",     (0, 1), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",    (0, 1), (0, -1),  DARK),
        ("TEXTCOLOR",    (1, 1), (1, -1),  GREY_TEXT),
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle(style))
    return t


def _page_footer(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(GREY_TEXT)
    canvas_obj.drawString(
        0.75 * inch,
        0.5 * inch,
        "Evidentix™ | evidenceanalyzer.com | Confidential — For Legal Use Only",
    )
    canvas_obj.drawRightString(
        letter[0] - 0.75 * inch,
        0.5 * inch,
        f"Page {doc.page}",
    )
    canvas_obj.restoreState()


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_comparison_pdf(comparison_result, output_path):
    """
    Build a styled forensic comparison PDF.

    comparison_result keys used:
        suspect_file, reference_file
        suspect_hash, reference_hash
        suspect_phash, reference_phash
        similarity_score, phash_distance, sha256_match
        confidence_level   — from build_forensic_conclusion()
        conclusion_title   — from build_forensic_conclusion()
        conclusion_text    — from build_forensic_conclusion()
        interpretation_text— from build_forensic_conclusion()
        limitations_text   — REPORT_LIMITATIONS_TEXT constant
        differences        — list of dicts or strings
        analysis_date
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    body_style, small_style, label_style, mono_style, footer_style = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.9 * inch,
    )
    content_width = letter[0] - 1.5 * inch

    # ── Extract payload values ─────────────────────────────────────────────────
    suspect_file    = comparison_result.get("suspect_file") or "Unknown"
    reference_file  = comparison_result.get("reference_file") or "Unknown"
    suspect_hash    = comparison_result.get("suspect_hash") or "Not Available"
    reference_hash  = comparison_result.get("reference_hash") or "Not Available"
    suspect_phash   = comparison_result.get("suspect_phash") or "Not Available"
    reference_phash = comparison_result.get("reference_phash") or "Not Available"
    similarity_score= float(comparison_result.get("similarity_score") or 0)
    phash_distance  = comparison_result.get("phash_distance", "—")
    sha256_match    = comparison_result.get("sha256_match")

    # Use conclusion data passed from build_forensic_conclusion() — never re-derive
    confidence_level    = comparison_result.get("confidence_level") or comparison_result.get("classification") or "—"
    conclusion_title    = comparison_result.get("conclusion_title") or confidence_level
    conclusion_text     = comparison_result.get("conclusion_text") or ""
    interpretation_text = comparison_result.get("interpretation_text") or ""
    limitations_text    = comparison_result.get("limitations_text") or (
        "This report does not determine authorship, ownership, or legal infringement. "
        "Metadata may be incomplete, absent, or altered. Conclusions are based solely "
        "on the digital characteristics of the submitted files."
    )
    differences = comparison_result.get("differences") or []
    analysis_date = comparison_result.get("analysis_date") or datetime.utcnow().isoformat()

    sha_label = {True: "Exact Match", False: "No Match", None: "Not Compared"}.get(sha256_match, "—")

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(HeaderBanner(
        "Forensic Image Comparison Report",
        f"Generated by Evidentix™  |  {analysis_date[:19].replace('T', '  ')}  UTC",
        content_width,
    ))
    story.append(Spacer(1, 14))

    # ── Verdict box ───────────────────────────────────────────────────────────
    story.append(VerdictBox(confidence_level, conclusion_title, content_width))
    story.append(Spacer(1, 16))

    # ── Section 1: File Identification ────────────────────────────────────────
    story.append(SectionHeading(1, "File Identification", content_width))
    story.append(Spacer(1, 8))

    col = [content_width * 0.32, content_width * 0.68]
    id_rows = [
        ["Suspect File",   suspect_file],
        ["Reference File", reference_file],
    ]
    story.append(_metric_table(id_rows, col))
    story.append(Spacer(1, 10))

    # Hashes in mono
    story.append(Paragraph("SHA-256 Hashes", label_style))
    story.append(Spacer(1, 3))
    hash_rows = [
        ["Suspect",   Paragraph(suspect_hash,   mono_style)],
        ["Reference", Paragraph(reference_hash, mono_style)],
    ]
    story.append(_metric_table(hash_rows, col))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Perceptual Hashes (pHash)", label_style))
    story.append(Spacer(1, 3))
    phash_rows = [
        ["Suspect",   Paragraph(suspect_phash,   mono_style)],
        ["Reference", Paragraph(reference_phash, mono_style)],
    ]
    story.append(_metric_table(phash_rows, col))
    story.append(Spacer(1, 16))

    # ── Section 2: Comparison Metrics ─────────────────────────────────────────
    story.append(SectionHeading(2, "Comparison Metrics", content_width))
    story.append(Spacer(1, 8))

    metric_rows = [
        ["SHA-256 Match",      sha_label],
        ["pHash Distance",     str(phash_distance)],
        ["Similarity Score",   f"{similarity_score:.2f}%"],
        ["Confidence Level",   confidence_level],
    ]
    story.append(_metric_table(metric_rows, col))
    story.append(Spacer(1, 16))

    # ── Section 3: Forensic Conclusion ────────────────────────────────────────
    story.append(SectionHeading(3, "Forensic Conclusion", content_width))
    story.append(Spacer(1, 8))

    if conclusion_text:
        story.append(Paragraph(conclusion_text, body_style))
        story.append(Spacer(1, 6))

    if interpretation_text:
        story.append(Paragraph(interpretation_text, small_style))

    story.append(Spacer(1, 16))

    # ── Section 4: Observed Differences ──────────────────────────────────────
    story.append(SectionHeading(4, "Observed Differences", content_width))
    story.append(Spacer(1, 8))

    diff_col = [content_width * 0.30, content_width * 0.70]
    if differences:
        diff_t = _diff_table(differences, diff_col)
        if diff_t:
            story.append(diff_t)
        else:
            for d in differences:
                story.append(Paragraph(f"• {d}", body_style))
    else:
        story.append(Paragraph(
            "No significant distinguishing differences were recorded beyond those ordinarily "
            "consistent with recompression, resizing, or metadata variation.",
            body_style,
        ))
    story.append(Spacer(1, 16))

    # ── Section 5: Technical Methodology ──────────────────────────────────────
    story.append(KeepTogether([
        SectionHeading(5, "Technical Methodology", content_width),
        Spacer(1, 8),
        Paragraph(
            "This analysis applies a multi-factor forensic methodology combining: "
            "(1) Cryptographic hash comparison (SHA-256) for exact file identity; "
            "(2) Perceptual hash comparison (pHash) for visual similarity under encoding variations; "
            "(3) Structural Similarity Index (SSIM) for pixel-level image structure analysis; "
            "(4) Metadata and EXIF differential review. "
            "No single metric is determinative in isolation. Conclusions reflect the combined "
            "weight of all observed indicators.",
            body_style,
        ),
        Spacer(1, 16),
    ]))

    # ── Section 6: Limitations ────────────────────────────────────────────────
    story.append(KeepTogether([
        SectionHeading(6, "Limitations & Scope", content_width),
        Spacer(1, 8),
        Paragraph(limitations_text, small_style),
        Spacer(1, 16),
    ]))

    # ── Section 7: Reproducibility ────────────────────────────────────────────
    story.append(KeepTogether([
        SectionHeading(7, "Reproducibility", content_width),
        Spacer(1, 8),
        Paragraph(
            "All analysis steps are reproducible using identical input files within the "
            "Evidentix™ platform (evidenceanalyzer.com). Results may differ if input files "
            "have been further modified, re-encoded, or recompressed prior to resubmission.",
            small_style,
        ),
        Spacer(1, 20),
    ]))

    # ── Footer rule ───────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY_LINE))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report was generated by Evidentix™ automated forensic analysis software. "
        "It does not constitute legal advice. For evidentiary use, consult qualified counsel.",
        footer_style,
    ))

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return output_path
