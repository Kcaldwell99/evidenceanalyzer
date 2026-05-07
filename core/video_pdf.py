# Evidentix video forensic PDF — generated 2026-05-06
"""Generate forensic PDF report for video analysis results.

Modeled on core/comparison_pdf.py for visual consistency.
Imports brand palette and flowables from comparison_pdf to avoid duplication.
"""

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
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from core.comparison_pdf import (
    HeaderBanner, SectionHeading,
    PURPLE, PURPLE_LIGHT, PURPLE_BG, DARK, GREY_LINE, GREY_TEXT, WHITE,
)


def _styles():
    """Build paragraph styles for the video PDF."""
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "VidBody", parent=base["Normal"],
        fontName="Helvetica", fontSize=10, leading=14, textColor=DARK,
    )
    mono = ParagraphStyle(
        "VidMono", parent=base["Normal"],
        fontName="Courier", fontSize=8, leading=11, textColor=DARK,
    )
    note = ParagraphStyle(
        "VidNote", parent=base["Normal"],
        fontName="Helvetica-Oblique", fontSize=9, leading=12, textColor=GREY_TEXT,
    )
    return {"body": body, "mono": mono, "note": note}


def _kv_table(rows, total_width):
    """Build a 2-column key/value table for metadata sections."""
    table = Table(rows, colWidths=[total_width * 0.35, total_width * 0.65])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY_TEXT),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, GREY_LINE),
    ]))
    return table


def _format_metadata(metadata: dict) -> list:
    """Convert ffmpeg metadata dict to display rows."""
    if not metadata or not isinstance(metadata, dict):
        return [["Metadata", "Not available"]]
    rows = []
    keys_in_order = [
        ("format", "Container Format"),
        ("codec", "Video Codec"),
        ("duration", "Duration"),
        ("width", "Width"),
        ("height", "Height"),
        ("fps", "Frame Rate (fps)"),
        ("bitrate", "Bitrate"),
        ("size_bytes", "File Size (bytes)"),
    ]
    for key, label in keys_in_order:
        if key in metadata and metadata[key] not in (None, "", "None"):
            rows.append([label, str(metadata[key])])
    return rows or [["Metadata", "No structured fields available"]]


def generate_video_pdf(result: dict, output_path: str) -> str:
    """Generate forensic PDF report from analyze_video() result.

    Args:
        result: dict returned by core.video_analyzer.analyze_video()
        output_path: full path where PDF will be written

    Returns:
        output_path (for caller convenience)
    """
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.5 * inch, bottomMargin=0.75 * inch,
        title=f"Video Forensic Report — {result.get('file_name', 'video')}",
    )
    page_width = letter[0] - (1.5 * inch)
    story = []

    # Header banner
    file_name = result.get("file_name", "Unknown")
    timestamp = result.get("analysis_date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    story.append(HeaderBanner(
        title="Video Forensic Analysis",
        subtitle=f"{file_name}  ·  Generated {timestamp}",
        width=page_width,
    ))
    story.append(Spacer(1, 18))

    # Section 1 — File Identification
    story.append(SectionHeading(1, "File Identification", page_width))
    story.append(Spacer(1, 8))
    sha256 = result.get("sha256", "Not computed")
    sha_para = Paragraph(f"<font name='Courier' size='8'>{sha256}</font>", styles["body"])
    story.append(_kv_table([
        ["File Name", result.get("file_name", "—")],
        ["SHA-256 Hash", sha_para],
        ["File Type", result.get("type", "video")],
        ["Analysis Date", timestamp],
    ], page_width))
    story.append(Spacer(1, 16))

    # Section 2 — Video Metadata
    story.append(SectionHeading(2, "Video Metadata", page_width))
    story.append(Spacer(1, 8))
    meta_rows = _format_metadata(result.get("metadata"))
    story.append(_kv_table(meta_rows, page_width))
    story.append(Spacer(1, 16))

    # Section 3 — Frame Analysis Summary
    story.append(SectionHeading(3, "Frame Analysis Summary", page_width))
    story.append(Spacer(1, 8))
    story.append(_kv_table([
        ["Total Frames in Source", str(result.get("total_frames", "—"))],
        ["Frames Extracted for Analysis", str(result.get("frames_extracted", "—"))],
        ["Sampling Interval (seconds)", str(result.get("interval_seconds", "—"))],
        ["Source Frame Rate (fps)", str(result.get("fps", "—"))],
    ], page_width))
    story.append(Spacer(1, 16))

    # Section 4 — Frame Hash Sample (first 10 + last 10)
    story.append(SectionHeading(4, "Frame Hash Sample", page_width))
    story.append(Spacer(1, 8))
    frame_hashes = result.get("frame_hashes", []) or []
    total_hashes = len(frame_hashes)

    if total_hashes == 0:
        story.append(Paragraph("No frame hashes available.", styles["note"]))
    elif total_hashes <= 20:
        # Small enough — show all
        rows = [["Frame #", "Perceptual Hash (pHash)"]]
        for idx, h in enumerate(frame_hashes, start=1):
            rows.append([str(idx), str(h)])
        hash_table = Table(rows, colWidths=[page_width * 0.15, page_width * 0.85])
        hash_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica"),
            ("FONTNAME", (1, 1), (1, -1), "Courier"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 1), (-1, -1), DARK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, GREY_LINE),
        ]))
        story.append(hash_table)
    else:
        # Show first 10 + last 10
        first = list(enumerate(frame_hashes[:10], start=1))
        last_start = total_hashes - 10 + 1
        last = list(enumerate(frame_hashes[-10:], start=last_start))
        rows = [["Frame #", "Perceptual Hash (pHash)"]]
        for idx, h in first:
            rows.append([str(idx), str(h)])
        rows.append(["…", f"({total_hashes - 20} additional frames not shown — see JSON sidecar)"])
        for idx, h in last:
            rows.append([str(idx), str(h)])
        hash_table = Table(rows, colWidths=[page_width * 0.15, page_width * 0.85])
        hash_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica"),
            ("FONTNAME", (1, 1), (1, -1), "Courier"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
            ("TEXTCOLOR", (0, 1), (-1, -1), DARK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, GREY_LINE),
            # Subtle background on the elision row
            ("BACKGROUND", (0, 11), (-1, 11), PURPLE_BG),
            ("FONTNAME", (0, 11), (-1, 11), "Helvetica-Oblique"),
            ("TEXTCOLOR", (0, 11), (-1, 11), GREY_TEXT),
        ]))
        story.append(hash_table)
    story.append(Spacer(1, 16))

    # Section 5 — Methodology Note
    story.append(SectionHeading(5, "Methodology", page_width))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Frames were extracted from the source video at the sampling interval shown in "
        "Section 3. For each extracted frame, a perceptual hash (pHash) was computed. "
        "These hashes serve two purposes: (1) they enable detection of frame-level tampering "
        "by comparing this report against any subsequent re-analysis of the same source file, "
        "and (2) they enable comparison against other video files for similarity analysis. "
        "The full list of frame hashes is preserved in the accompanying JSON sidecar.",
        styles["body"],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This report documents the analysis performed by Evidentix at the timestamp shown "
        "in Section 1. It does not, by itself, establish the authenticity or provenance of "
        "the source video; it documents what was observed during analysis.",
        styles["note"],
    ))

    doc.build(story)
    return output_path