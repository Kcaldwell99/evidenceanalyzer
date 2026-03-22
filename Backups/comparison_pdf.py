import os
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _safe_str(value, default="N/A"):
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _draw_wrapped_text(c, text, x, y, max_width, line_height=14, font_name="Helvetica", font_size=10):
    """
    Draw wrapped text onto the canvas and return the new Y position.
    """
    c.setFont(font_name, font_size)

    words = str(text).split()
    if not words:
        return y - line_height

    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = word

    if line:
        c.drawString(x, y, line)
        y -= line_height

    return y


def _draw_section_title(c, title, x, y):
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(x, y, title)
    return y - 16


def _draw_label_value(c, label, value, x, y, label_width=150, font_size=10):
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(x, y, f"{label}")
    c.setFont("Helvetica", font_size)
    c.drawString(x + label_width, y, _safe_str(value))
    return y - 14


def _draw_image_fit(c, image_path, x, y_top, max_width, max_height, label=None):
    """
    Draw an image proportionally scaled to fit within max_width/max_height.
    y_top is the top edge for placement.
    Returns the bottom y position after drawing.
    """
    if not image_path or not os.path.exists(image_path):
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(x, y_top - 12, f"{label or 'Image'} not available.")
        return y_top - 20

    try:
        img = ImageReader(image_path)
        iw, ih = img.getSize()
    except Exception:
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(x, y_top - 12, f"{label or 'Image'} could not be loaded.")
        return y_top - 20

    scale = min(max_width / iw, max_height / ih)
    draw_w = iw * scale
    draw_h = ih * scale

    if label:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y_top - 12, label)
        y_top -= 18

    y_image_bottom = y_top - draw_h
    c.drawImage(
        image_path,
        x,
        y_image_bottom,
        width=draw_w,
        height=draw_h,
        preserveAspectRatio=True,
        mask="auto",
    )

    return y_image_bottom - 10


def _ensure_page_space(c, y, needed_space=120, margin_bottom=60):
    """
    Starts a new page if there is not enough vertical room.
    Returns the new/current y position.
    """
    if y < margin_bottom + needed_space:
        c.showPage()
        return 750
    return y


def generate_comparison_pdf(comparison_result: dict, output_pdf_path: str):
    """
    Generate a forensic-style comparison PDF report.

    comparison_result expected fields may include:
        matched_case
        matched_evidence
        file_name
        suspect_file_name
        similarity_score
        match_level
        ssim_score
        similarity_percent
        visual_assessment
        difference_regions
        side_by_side_path
        heatmap_path
        original_marked_path
        suspect_marked_path
        source_url
        analysis_date
    """
    Path(os.path.dirname(output_pdf_path)).mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(output_pdf_path, pagesize=letter)
    width, height = letter

    left_margin = 50
    right_margin = 50
    usable_width = width - left_margin - right_margin
    y = 750

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left_margin, y, "Digital Evidence Comparison Report")
    y -= 24

    c.setFont("Helvetica", 10)
    report_date = comparison_result.get("analysis_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.drawString(left_margin, y, f"Generated: {report_date}")
    y -= 22

    c.setStrokeColor(colors.grey)
    c.line(left_margin, y, width - right_margin, y)
    y -= 20

    # Summary Section
    y = _draw_section_title(c, "1. Comparison Summary", left_margin, y)
    y = _draw_label_value(c, "Reference File:", comparison_result.get("file_name"), left_margin, y)
    y = _draw_label_value(c, "Comparison File:", comparison_result.get("suspect_file_name"), left_margin, y)
    y = _draw_label_value(c, "Matched Case:", comparison_result.get("matched_case"), left_margin, y)
    y = _draw_label_value(c, "Matched Evidence ID:", comparison_result.get("matched_evidence"), left_margin, y)
    y = _draw_label_value(c, "Perceptual Similarity Score:", comparison_result.get("similarity_score"), left_margin, y)
    y = _draw_label_value(c, "Match Level:", comparison_result.get("match_level"), left_margin, y)

    source_url = comparison_result.get("source_url")
    if source_url:
        y = _ensure_page_space(c, y, needed_space=50)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, y, "Source URL:")
        y -= 14
        c.setFont("Helvetica", 9)
        y = _draw_wrapped_text(c, source_url, left_margin, y, usable_width, line_height=12, font_size=9)

    y -= 10

    # Visual Analysis Section
    visual_fields_present = any(
        comparison_result.get(key) is not None
        for key in [
            "ssim_score",
            "similarity_percent",
            "visual_assessment",
            "difference_regions",
            "side_by_side_path",
            "heatmap_path",
            "original_marked_path",
            "suspect_marked_path",
        ]
    )

    if visual_fields_present:
        y = _ensure_page_space(c, y, needed_space=180)
        y = _draw_section_title(c, "2. Visual Difference Analysis", left_margin, y)

        y = _draw_label_value(c, "SSIM Score:", comparison_result.get("ssim_score"), left_margin, y)
        y = _draw_label_value(c, "Similarity Percent:", 
                              f"{comparison_result.get('similarity_percent')}%" if comparison_result.get("similarity_percent") is not None else "N/A",
                              left_margin, y)
        y = _draw_label_value(c, "Visual Assessment:", comparison_result.get("visual_assessment"), left_margin, y)
        y = _draw_label_value(c, "Difference Regions:", comparison_result.get("difference_regions"), left_margin, y)

        explanatory_text = (
            "This section reflects structural similarity analysis performed after "
            "normalizing the compared images to common dimensions. Highlighted regions "
            "indicate localized areas of detected divergence between the reference image "
            "and the comparison image."
        )
        y -= 4
        y = _draw_wrapped_text(
            c,
            explanatory_text,
            left_margin,
            y,
            usable_width,
            line_height=12,
            font_name="Helvetica",
            font_size=9,
        )
        y -= 10

        # Side-by-side
        side_by_side_path = comparison_result.get("side_by_side_path")
        if side_by_side_path:
            y = _ensure_page_space(c, y, needed_space=240)
            y = _draw_image_fit(
                c,
                side_by_side_path,
                left_margin,
                y,
                max_width=usable_width,
                max_height=220,
                label="Side-by-Side Comparison",
            )

        # Heatmap
        heatmap_path = comparison_result.get("heatmap_path")
        if heatmap_path:
            y = _ensure_page_space(c, y, needed_space=240)
            y = _draw_image_fit(
                c,
                heatmap_path,
                left_margin,
                y,
                max_width=usable_width,
                max_height=220,
                label="Difference Heatmap",
            )

        # Marked images on separate pages if needed
        original_marked_path = comparison_result.get("original_marked_path")
        suspect_marked_path = comparison_result.get("suspect_marked_path")

        if original_marked_path:
            y = _ensure_page_space(c, y, needed_space=260)
            y = _draw_image_fit(
                c,
                original_marked_path,
                left_margin,
                y,
                max_width=usable_width,
                max_height=240,
                label="Reference Image with Marked Difference Regions",
            )

        if suspect_marked_path:
            y = _ensure_page_space(c, y, needed_space=260)
            y = _draw_image_fit(
                c,
                suspect_marked_path,
                left_margin,
                y,
                max_width=usable_width,
                max_height=240,
                label="Comparison Image with Marked Difference Regions",
            )

    # Conclusion
    y = _ensure_page_space(c, y, needed_space=120)
    y = _draw_section_title(c, "3. Observations", left_margin, y)

    match_level = _safe_str(comparison_result.get("match_level"))
    visual_assessment = _safe_str(comparison_result.get("visual_assessment"), default="No visual assessment available")

    observation_text = (
        f"The compared files produced a perceptual match classification of {match_level}. "
        f"Visual difference analysis assessed the image pair as {visual_assessment.lower()}. "
        f"These results should be considered together with cryptographic hash values, metadata, "
        f"provenance indicators, and any surrounding investigative context."
    )

    y = _draw_wrapped_text(
        c,
        observation_text,
        left_margin,
        y,
        usable_width,
        line_height=13,
        font_name="Helvetica",
        font_size=10,
    )

    y -= 10
    c.setFont("Helvetica-Oblique", 9)
    disclaimer = (
        "This report is intended as an analytical aid and does not by itself establish "
        "authorship, ownership, publication date, or legal infringement."
    )
    _draw_wrapped_text(
        c,
        disclaimer,
        left_margin,
        y,
        usable_width,
        line_height=12,
        font_name="Helvetica-Oblique",
        font_size=9,
    )

    c.save()
    return output_pdf_path