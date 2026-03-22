from core.hashing import sha256_file
from core.metadata import get_image_metadata
from core.pdf_report import create_pdf_report
from core.c2pa_check import check_c2pa_presence
import sys
import json
import os
from datetime import datetime

reports_root = "reports"
os.makedirs(reports_root, exist_ok=True)

case_folder = datetime.now().strftime("%Y-%m-%d_%H%M%S")
case_path = os.path.join(reports_root, case_folder)
os.makedirs(case_path, exist_ok=True)


def analyze_file(file_path, case_path):
    file_hash = sha256_file(file_path)
    file_size = os.path.getsize(file_path)
    image_metadata = get_image_metadata(file_path)
    c2pa_info = check_c2pa_presence(file_path)

    report = {
        "file_name": os.path.basename(file_path),
        "file_path": os.path.abspath(file_path),
        "sha256": file_hash,
        "size_bytes": file_size,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "image_metadata": image_metadata,
        "c2pa": c2pa_info
    }

    report["copyright_search"] = {
        "title": "",
        "author": "",
        "claimant": "",
        "registration_number": "",
        "year": "",
        "search_link": "",
        "note": (
        "Public records may indicate registration or recorded transfer information, "
        "but do not conclusively establish present ownership."
    )
}
  
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    json_name = os.path.join(case_path, f"{base_name}_evidence_report.json")
    pdf_name = os.path.join(case_path, f"{base_name}_evidence_report.pdf")

    with open(json_name, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)

    create_pdf_report(report, pdf_name)

    print("Analyzed:", file_path)
    print("SHA256:", file_hash)
    print("Saved:", json_name)
    print("Saved:", pdf_name)

    return report, json_name, pdf_name