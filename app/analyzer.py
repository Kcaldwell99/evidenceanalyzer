import json
import os
import textwrap
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.utils.hash_utils import sha256_file
from app.utils.metadata_utils import get_image_metadata, extract_exif
from app.utils.c2pa_utils import check_c2pa_presence
from app.utils.image_fingerprint import generate_phash
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

def analyze_file(file_path, case_dir=None):
    file_hash = sha256_file(file_path)
    file_size = os.path.getsize(file_path)
    image_metadata = get_image_metadata(file_path)
    exif_data = extract_exif(file_path)
    c2pa_info = check_c2pa_presence(file_path)
    phash = generate_phash(file_path)

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
        "c2pa": c2pa_info,
        "analysis_date": datetime.utcnow().isoformat(),
        "similar_matches": similar_matches[:5],
    }

    report["metadata_status"] = (
        "present" if exif_data and "error" not in exif_data else "missing"
    )

    if c2pa_info.get("present"):
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
            "No embedded metadata detected. This may indicate that metadata was removed "
            "during transmission, editing, export, or platform processing. The absence "
            "of metadata limits forensic verification of device origin, capture time, "
            "and location."
        )

    report["rights_info"] = {
        "Original Copyright Owner": "Must Request Separate Report",
        "Copyright Registration": "Must Request Separate Report",
        "Copyright Contact": "Must Request Separate Report",
        "Copyright Assignments": "Must Request Separate Report",
    }

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

    json_path = os.path.join(case_path, "analysis_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    pdf_path = os.path.join(case_path, "analysis_report.pdf")

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    y = height - 50

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Evidentix Analysis Report")
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
    y -= 8

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
    c.drawString(50, y, "4. Rights & Ownership (Preliminary)")
    y -= 15

    c.setFont("Helvetica", 10)
    rights = report.get("rights_info", {})
    for key, value in rights.items():
        y = _draw_wrapped_lines(c, [f"{key}: {value}"], 60, y)

    y = _draw_wrapped_lines(
        c,
        _wrap_text(
            "Ownership information is preliminary and based solely on available file data "
            "and observable indicators."
        ),
        60,
        y - 4,
    )
    y = _draw_wrapped_lines(
        c,
        _wrap_text(
            "No independent verification of copyright registration, transfer, assignment, "
            "or licensing status has been performed."
        ),
        60,
        y,
    )

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "5. Conclusion")
    y -= 15

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_lines(
        c,
        _wrap_text(f"Finding: {report.get('finding', 'No finding available')}"),
        60,
        y,
    )

    c.save()

    if case_dir and case_id_value and evidence_id:
        case_root = os.path.dirname(case_dir)
        relative_json_path = os.path.relpath(json_path, start=case_root).replace("\\", "/")
        relative_pdf_path = os.path.relpath(pdf_path, start=case_root).replace("\\", "/")

        db = SessionLocal()
        try:
            db_item = EvidenceItem(
                case_id=case_id_value,
                evidence_id=evidence_id,
                file_name=os.path.basename(file_path),
                sha256=file_hash,
                phash=phash,
                analysis_date=report["analysis_date"],
                json_report=relative_json_path,
                pdf_report=relative_pdf_path,
                file_key=file_key,
            )
            db.add(db_item)
            db.commit()
        finally:
            db.close()

        add_fingerprint(
            case_id_value,
            evidence_id,
            os.path.basename(file_path),
            phash,
            relative_pdf_path,
            relative_json_path,
        )

    return report, json_path, pdf_path
