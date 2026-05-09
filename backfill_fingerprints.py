import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import SessionLocal
from app.models import EvidenceItem
from app.storage import download_to_tempfile
from app.utils.image_fingerprint import generate_phash
from core.fingerprint_index import add_fingerprint

db = SessionLocal()
items = db.query(EvidenceItem).filter(EvidenceItem.file_key != None).all()
db.close()

print(f"Found {len(items)} evidence items to index")

for item in items:
    try:
        suffix = os.path.splitext(item.file_name)[1]
        tmp_path = download_to_tempfile(item.file_key, suffix=suffix)
        phash = generate_phash(tmp_path)
        os.remove(tmp_path)

        if phash is None:
            print(f"Skipped (no phash): {item.file_name} ({item.case_id})")
            continue

        add_fingerprint(
            case_id=item.case_id,
            evidence_id=item.evidence_id,
            file_name=item.file_name,
            phash=phash,
            pdf_report=item.pdf_report,
            json_report=item.json_report,
        )
        print(f"Indexed: {item.file_name} ({item.case_id})")
    except Exception as e:
        print(f"Failed: {item.file_name} — {e}")

print("Done.")
