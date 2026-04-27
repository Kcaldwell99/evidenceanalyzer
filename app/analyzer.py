import json
import os
import textwrap
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.utils.hash_utils import sha256_file
from app.utils.metadata_utils import get_image_metadata, extract_exif
from app.c2pa_analysis import analyze_file as c2pa_analyze_file, summarize_for_certificate
from app.utils.image_fingerprint import generate_phash
from app.utils.web_detection import detect_web_presence
from app.utils.hash_compare import hamming_distance

from core.fingerprint_index import add_fingerprint, search_similar
from app.db import SessionLocal
from app.models import EvidenceItem


def _wrap_text(text, width=95):
    if text is None:
        return [""]
    return textwrap.wrap(str(text), width=width) or [""]


def _draw_wrapped_lines(c, lines, x, y, line_height=12, bottom_margin=50):
    for line in lines:
        if y <= bottom_margin:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = letter[1] - 50
        c.drawString(x, y, line)
        y -= line_height
    return y

def analyze_file(file_path, case_dir=None, file_key=None, original_filename=None):
    file_hash = sha256_file(file_path)
    file_size = os.path.getsize(file_path)
    image_metadata = get_image_metadata(file_path)
    exif_data = extract_exif(file_path)
    c2pa_info = c2pa_analyze_file(file_path)
    c2pa_summary = summarize_for_certificate(c2pa_info)
    phash = generate_phash(file_path)
    web_detection = detect_web_presence(file_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if case_dir:
        case_path = os.path.join(case_dir, "reports", timestamp)
    else:
        case_path = os.path.join("reports", timestamp)

    os.makedirs(case_path, exist_ok=True)

    evidence_id = None
    case_id_value = None

    if case_dir:
        case_id_value = os.path.basename(case_dir)
        db = SessionLocal()
        try:
            existing_count = (
                db.query(EvidenceItem)
                .filter(EvidenceItem.case_id == case_id_value)
                .count()
            )
            evidence_id = f"E-{existing_count + 1:03d}"
        finally:
            db.close()
    add_fingerprint(
        case_id=case_id_value,
        evidence_id=evidence_id,
        file_name=original_filename or os.path.basename(file_path),
        phash=phash,
    )

    similar_matches = search_similar(
        phash,
        hamming_distance,
        max_distance=8,
    )

    report = {
        "evidence_id": evidence_id,
        "file_name": os.path.basename(file_path),
        "file_size": file_size,
        "sha256": file_hash,
        "phash": phash,
        "metadata": image_metadata,
        "exif": exif_data,
        "c2pa": c2pa_summary,
        "analysis_date": datetime.utcnow().isoformat(),
        "similar_matches": similar_matches[:5],
        "web_detection": web_detection,
    }

    report["metadata_status"] = (
        "present" if exif_data and "error" not in exif_data else "missing"
    )
    if c2pa_summary.get("state") not in ("ABSENT", "UNAVAILABLE", None):
            report["finding"] = (
            "Provenance data present. No obvious integrity concerns were identified "
            "from the available file-level indicators reviewed."
        )
    elif exif_data and "error" not in exif_data and exif_data != {}:
        report["finding"] = (
            "EXIF metadata detected. No obvious manipulation indicators were identified "
            "from the file-level metadata reviewed."
        )
    elif image_metadata:
        report["finding"] = (
            "Basic metadata detected. No obvious manipulation indicators were identified "
            "from the available file-level data reviewed."
        )
    else:
        report["finding"] = (
            "No embedded metadata was detected in the submitted file. The absence of metadata may be "
            "consistent with removal during transmission, editing, export, or platform processing. "
            "This limits file-level attribution regarding device origin, capture time, and location."
        )

    if report["similar_matches"]:
        best_match = report["similar_matches"][0]
        report["comparison_summary"] = (
            f"Potential prior match identified: {best_match.get('file_name')} "
            f"(Case {best_match.get('case_id')}, Evidence {best_match.get('evidence_id')}) "
            f"with similarity score {best_match.get('similarity')}% and match level "
            f"{best_match.get('match_level')}."
        )
    else:
        report["comparison_summary"] = (
            "No prior similar image match was identified within the configured threshold."
        )

    if report["similar_matches"]:
        best_match = report["similar_matches"][0]
        similarity = best_match.get("similarity", 0)

        if similarity >= 90:
            confidence = "High Confidence Match"
        elif similarity >= 75:
            confidence = "Probable Match"
        else:
            confidence = "Inconclusive"

      
        report["similarity_assessment"] = confidence
    else:
        report["similarity_assessment"] = "No similar prior file identified"

    report["methodology"] = (
        "The submitted file was analyzed using a combination of forensic techniques, including "
        "SHA-256 hashing for file integrity verification, perceptual hashing for structural similarity, "
        "metadata and EXIF analysis, and comparison against previously indexed evidence. "
        "Where applicable, visual comparison techniques were used to identify structural and compositional similarities."
    )

    report["limitations"] = (
        "This report reflects a tool-assisted forensic analysis of the submitted file. "
        "It does not independently establish authorship, ownership, or legal infringement. "
        "Metadata may be altered or removed during processing or transmission. "
        "Conclusions are limited to the observable characteristics of the files analyzed."
    )
    confidence = report.get("similarity_assessment")

    if confidence == "High Confidence Match":
        report["preliminary_conclusion"] = (
            "The submitted image exhibits a high degree of similarity to previously indexed evidence. "
            "The available indicators support the conclusion that the image is likely derived from "
            "the same source or an altered version of the same original image."
    )
    elif confidence == "Probable Match":
        report["preliminary_conclusion"] = (
            "The submitted image exhibits notable similarity to previously indexed evidence. "
            "The indicators suggest a probable relationship between the images, although differences "
            "may reflect editing, recompression, or transformation."
    )
    else:
        report["preliminary_conclusion"] = (
            "The submitted image does not exhibit sufficient similarity to support a reliable "
            "forensic conclusion of derivation from previously indexed evidence." 
    )

 # After line 187, add:
    json_path = os.path.join(case_path, "analysis_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    pdf_path = os.path.join(case_path, "analysis_report.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    y = height - 50

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Evidentix\u2122 Analysis Report")
    y -= 25

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "1. File Information")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(c, [f"Evidence ID: {report.get('evidence_id', 'Not Assigned')}"], 60, y)
    y = _draw_wrapped_lines(c, [f"File Name: {report.get('file_name', 'Not Available')}"], 60, y)
    y = _draw_wrapped_lines(c, [f"File Size: {report.get('file_size', 'Not Available')} bytes"], 60, y)
    y = _draw_wrapped_lines(c, [f"SHA256: {report.get('sha256', 'Not Available')}"], 60, y)
    y = _draw_wrapped_lines(c, [f"Perceptual Hash (pHash): {report.get('phash', 'Not Available')}"], 60, y)
    y -= 8

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "2. Metadata Review")
    y -= 15

    c.setFont("Helvetica", 10)
    exif = report.get("exif", {})
    metadata = report.get("metadata")

    if exif and "error" not in exif:
        y = _draw_wrapped_lines(c, ["EXIF metadata detected in the submitted file."], 60, y)
        y = _draw_wrapped_lines(c, [f"Device: {exif.get('Model', 'Not Available')}"], 60, y)
        y = _draw_wrapped_lines(c, [f"Date Taken: {exif.get('DateTimeOriginal', 'Not Available')}"], 60, y)
        y = _draw_wrapped_lines(c, [f"Camera Make: {exif.get('Make', 'Not Available')}"], 60, y)
        y = _draw_wrapped_lines(c, [f"GPS Metadata Present: {'Yes' if 'GPSInfo' in exif else 'No'}"], 60, y)
    elif metadata:
        y = _draw_wrapped_lines(c, ["Basic metadata detected in the submitted file."], 60, y)
    else:
        y = _draw_wrapped_lines(
            c,
            _wrap_text(
                "No embedded metadata detected. This may indicate metadata was removed during "
                "processing or transmission."
            ),
            60,
            y,
        )
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "3. Similarity Review")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(c, _wrap_text(report.get("comparison_summary")), 60, y)

    if report["similar_matches"]:
        y -= 6
        for idx, match in enumerate(report["similar_matches"], start=1):
            match_text = (
                f"{idx}. File: {match.get('file_name')} | "
                f"Case: {match.get('case_id')} | "
                f"Evidence: {match.get('evidence_id')} | "
                f"Distance: {match.get('distance')} | "
                f"Similarity: {match.get('similarity')}% | "
                f"Level: {match.get('match_level')}"
            )
            y = _draw_wrapped_lines(c, _wrap_text(match_text), 60, y)
    else:
        y = _draw_wrapped_lines(c, ["No qualifying prior matches found."], 60, y)
    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "4. C2PA Content Credentials")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(c, _wrap_text(report.get("c2pa_summary", "Content Credentials not detected.")), 60, y)
   
    if c2pa_summary.get("flagged_ai"):
        y = _draw_wrapped_lines(c, ["WARNING: AI-generated content indicators detected in manifest."], 60, y)
    if c2pa_summary.get("flagged_no_credentials"):
        y = _draw_wrapped_lines(c, ["NOTE: No Content Credentials found. File provenance cannot be verified."], 60, y)

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "5. Web Presence Detection")

    y -= 15

    c.setFont("Helvetica", 10)
    web = report.get("web_detection", {})
    if web.get("error"):
        y = _draw_wrapped_lines(c, [f"Web detection unavailable: {web.get('error', '')}"], 60, y)
    else:
        labels = web.get("best_guess_labels", [])
        if labels:
            y = _draw_wrapped_lines(c, [f"Best Guess Labels: {', '.join(labels)}"], 60, y)

        full = web.get("full_matches", [])
        y = _draw_wrapped_lines(c, [f"Full Matches Found: {len(full)}"], 60, y)
        for m in full[:3]:
            y = _draw_wrapped_lines(c, _wrap_text(f"  - {m.get('url', '')}"), 60, y)

        partial = web.get("partial_matches", [])
        y = _draw_wrapped_lines(c, [f"Partial Matches Found: {len(partial)}"], 60, y)
        for m in partial[:3]:
            y = _draw_wrapped_lines(c, _wrap_text(f"  - {m.get('url', '')}"), 60, y)

        pages = web.get("pages_with_image", [])
        y = _draw_wrapped_lines(c, [f"Pages Containing Image: {len(pages)}"], 60, y)
        for p in pages[:3]:
            y = _draw_wrapped_lines(c, _wrap_text(f"  - {p.get('url', '')}"), 60, y)

        similar = web.get("visually_similar", [])
        y = _draw_wrapped_lines(c, [f"Visually Similar Images: {len(similar)}"], 60, y)

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "6. Forensic Conclusion")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(
        c,
        _wrap_text(f"Confidence Level: {report.get('similarity_assessment', 'Not available')}"),
        60,
        y,
    )
    y = _draw_wrapped_lines(
        c,
        _wrap_text(report.get("preliminary_conclusion", "")),
        60,
        y,
    )

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "7. Methodology")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(
        c,
        _wrap_text(report.get("methodology", "")),
        60,
        y,
    )

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "8. Limitations")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(
        c,
        _wrap_text(report.get("limitations", "")),
        60,
        y,
    )
    c.save()
    # Upload JSON and PDF to S3
    from app.storage import upload_file as s3_upload
    with open(json_path, "rb") as f:
        json_key = s3_upload(f, "analysis_report.json", "application/json")
    with open(pdf_path, "rb") as f:
        pdf_key = s3_upload(f, "analysis_report.pdf", "application/pdf")

    return report, json_key, pdf_key

