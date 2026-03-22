from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def create_pdf_report(report, output_file="evidence_report.pdf"):
    c = canvas.Canvas(output_file, pagesize=letter)
    width, height = letter

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Digital Evidence Report")

    y -= 30
    c.setFont("Helvetica", 11)

    c.drawString(50, y, f"File Name: {report['file_name']}")
    y -= 20
    c.drawString(50, y, f"File Path: {report['file_path']}")
    y -= 20
    c.drawString(50, y, f"SHA256: {report['sha256']}")
    y -= 20
    c.drawString(50, y, f"Size (bytes): {report['size_bytes']}")
    y -= 20
    c.drawString(50, y, f"Analyzed At: {report['analyzed_at']}")

    image_metadata = report.get("image_metadata", {})

    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Image Metadata")

    c.setFont("Helvetica", 11)
    y -= 20
    c.drawString(50, y, f"Format: {image_metadata.get('format')}")
    y -= 20
    c.drawString(50, y, f"Width: {image_metadata.get('width')}")
    y -= 20
    c.drawString(50, y, f"Height: {image_metadata.get('height')}")
    y -= 20
    c.drawString(50, y, f"Mode: {image_metadata.get('mode')}")

    c.save()