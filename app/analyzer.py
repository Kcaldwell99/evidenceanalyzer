import json
import os
import textwrap
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.utils.hash_utils import sha256_file
from app.utils.metadata_utils import get_image_metadata, extract_exif, extract_gps
from app.c2pa_analysis import analyze_file as c2pa_analyze_file, summarize_for_certificate
from app.utils.image_fingerprint import generate_phash
from app.utils.web_detection import detect_web_presence
from app.utils.map_render import render_map_png
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

def analyze_file(file_path, case_dir=None, file_key=None, original_filename=None, web_detection_enabled=False):
    file_hash = sha256_file(file_path)
    file_size = os.path.getsize(file_path)
    image_metadata = get_image_metadata(file_path)
    exif_data = extract_exif(file_path)
    gps_coords = extract_gps(file_path)
    print("DEBUG: starting C2PA analysis", flush=True)
    c2pa_info = c2pa_analyze_file(file_path)
    print("DEBUG: finished C2PA analysis", flush=True)
    c2pa_summary = summarize_for_certificate(c2pa_info)
    phash = generate_phash(file_path)
    if web_detection_enabled:
        web_detection = detect_web_presence(file_path)
    else:
        web_detection = {"skipped": "Web detection disabled by user."}

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
    if phash is not None:
        similar_matches = search_similar(
            phash,
            hamming_distance,
            max_distance=8,
        )
        add_fingerprint(
            case_id=case_id_value,
            evidence_id=evidence_id,
            file_name=original_filename or os.path.basename(file_path),
            phash=phash,
        )
    else:
        similar_matches = []
        # Phash unavailable for this file; skipping fingerprint indexing and
        # similarity search. Report will reflect this via the
        # report.get('phash') or 'Not Available' pattern at the rendering site.

    report = {
        "evidence_id": evidence_id,
        "file_name": os.path.basename(file_path),
        "file_size": file_size,
        "sha256": file_hash,
        "phash": phash,
        "metadata": image_metadata,
        "exif": exif_data,
        "gps_coords": gps_coords,
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

    # Upload JSON to S3
    from app.storage import upload_file as s3_upload
    with open(json_path, "rb") as f:
        json_key = s3_upload(f, "analysis_report.json", "application/json")

    return report, json_key, None

