from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

def generate_pdf_report(report: dict, pdf_path: str) -> None:
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    left = 50
    right = width - 50
    y = height - 50

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 50
        draw_page_frame()

    def ensure_space(lines_needed=1):
        nonlocal y
        if y < 70 + (lines_needed * 14):
            new_page()

    def draw_page_frame():
        page_no = c.getPageNumber()
        c.setFont("Helvetica", 9)
        c.drawString(left, 25, "CLF The Woodlands, LLC")
        c.drawCentredString(width / 2, 25, f"Page {page_no}")
        c.drawRightString(right, 25, "Evidence Analyzer™ / Evidentix™")
    
    def draw_text(text: str, font="Helvetica", size=11, x=left, leading=15):
        nonlocal y
        c.setFont(font, size)
        wrapped = simpleSplit(str(text), font, size, right - x)
        ensure_space(len(wrapped))
        for line in wrapped:
            c.drawString(x, y, line)
            y -= leading

    def draw_label_value(label: str, value, size=11):
        draw_text(f"{label}: {value}", size=size)

    def draw_section(title: str):
        nonlocal y
        y -= 6
        ensure_space(3)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(left, y, title)
        y -= 8
        c.line(left, y, right, y)
        y -= 16

    def draw_paragraph(text: str, size=11):
        draw_text(text, size=size)
        y_gap()

    def y_gap(amount=8):
        nonlocal y
        y -= amount

    file_name = report.get("file_name", "")
    file_size = report.get("file_size", "")
    sha256 = report.get("sha256", "")
    phash = report.get("phash", "")
    analysis_date = report.get("analysis_date", "")
    metadata = report.get("metadata", {}) or {}
    c2pa = report.get("c2pa", {}) or {}

    draw_page_frame()

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "Evidence Analyzer™")
    y -= 20

    c.setFont("Helvetica", 11)
    c.drawString(left, y, "CLF The Woodlands, LLC")
    y -= 15
    c.drawString(left, y, "Digital Image Forensic Analysis")
    y -= 25

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "Digital Image Forensic Report")
    y -= 22

    c.setFont("Helvetica", 11)
    c.drawString(left, y, f"Analysis Date: {analysis_date}")
    y -= 15
    c.drawString(left, y, f"File Name: {file_name}")
    y -= 20

    draw_section("1. Executive Summary")
    draw_paragraph(
        "This report presents a forensic analysis of the submitted digital image. "
        "The review includes cryptographic hashing, perceptual hashing, metadata extraction, "
        "and provenance review based on the information available in the submitted file."
    )

    draw_section("2. Image Details")
    draw_label_value("File Name", file_name)
    draw_label_value("File Size", file_size)
    draw_label_value("SHA-256", sha256, size=10)
    draw_label_value("Perceptual Hash (pHash)", phash, size=10)
    draw_label_value("Analysis Date", analysis_date)

    draw_section("3. Provenance / C2PA Review")
    draw_label_value("C2PA Present", c2pa.get("present", False))
    draw_text(f"Details: {c2pa.get('details', 'None reported')}", size=10)

    draw_section("4. Metadata Review")
    if isinstance(metadata, dict) and metadata:
        for key, value in metadata.items():
            draw_text(f"{key}: {value}", size=10)
    else:
        draw_text("No metadata was identified in the submitted file.", size=10)

    draw_section("5. Technical Notes")
    draw_paragraph(
        "SHA-256 is a cryptographic hash used to uniquely identify the exact file submitted for analysis. "
        "Perceptual hashing is used to identify visual similarity between images, even where file-level data differs."
    )
    draw_section("6. Rights & Ownership (Preliminary)")

    rights = report.get("rights_info", {})

    draw_label_value("Original Copyright Owner", "Information not Available in this Report")
    draw_label_value("Copyright Registration", "Information not Available in this Report")
    draw_label_value("Copyright Contact", "Information not Available in this Report")
    draw_label_value("Copyright Assignments", "Information not Available in this Report")

    draw_paragraph(
        "Ownership information is preliminary and based solely on available file data and observable indicators. "
        "No independent verification of copyright registration or assignment has been performed."
)

    draw_section("7. Conclusion")

# Simple finding (can refine later)

    finding = report.get("finding", "No indicators of manipulation detected")
  
    draw_text(f"Finding: {finding}", font="Helvetica-Bold", size=12)
    y_gap(6)


    draw_paragraph(
    "Based on the forensic indicators reviewed in the submitted file, this report identifies the technical "
    "characteristics observable from the image, including file integrity, metadata, perceptual fingerprinting, "
    "and any available provenance information. These findings may assist counsel, investigators, or retained experts "
    "in evaluating authenticity, alteration, copying, or derivation issues. Final conclusions should be considered "
    "together with all other available evidence."
)
    
    draw_section("7. Disclaimer")
    draw_paragraph(
        "This report is a technical forensic analysis generated for investigative and informational purposes. "
        "It does not constitute legal advice or expert testimony unless separately retained for that purpose."
    )

    draw_page_frame()
    c.save()

