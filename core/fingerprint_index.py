from app.db import SessionLocal
from app.models import FingerprintIndex


def add_fingerprint(case_id, evidence_id, file_name, phash, pdf_report=None, json_report=None):
    db = SessionLocal()
    try:
        existing = (
            db.query(FingerprintIndex)
            .filter(
                FingerprintIndex.case_id == case_id,
                FingerprintIndex.evidence_id == evidence_id,
            )
            .first()
        )

        if existing:
            existing.file_name = file_name
            existing.phash = phash
            existing.pdf_report = pdf_report
            existing.json_report = json_report
        else:
            record = FingerprintIndex(
                case_id=case_id,
                evidence_id=evidence_id,
                file_name=file_name,
                phash=phash,
                pdf_report=pdf_report,
                json_report=json_report,
            )
            db.add(record)

        db.commit()
    finally:
        db.close()


def search_similar(
    phash,
    distance_func,
    max_distance=8,
    exclude_case_id=None,
    exclude_evidence_id=None,
    exclude_file_name=None,
):
    db = SessionLocal()
    try:
        index = db.query(FingerprintIndex).all()
    finally:
        db.close()

    matches = []

    for item in index:
        item_phash = item.phash
        if not item_phash:
            continue

        if exclude_case_id and item.case_id == exclude_case_id:
            if exclude_evidence_id and item.evidence_id == exclude_evidence_id:
                continue

        if exclude_file_name and item.file_name == exclude_file_name:
            continue

        distance = distance_func(phash, item_phash)

        if distance > max_distance:
            continue

        similarity = max(0, 100 - (distance * 100 // 16))

        if distance <= 4:
            match_level = "High Match"
        elif distance <= 8:
            match_level = "Possible Match"
        elif distance <= 12:
            match_level = "Low Match"
        else:
            match_level = "Weak"

        matches.append({
            "case_id": item.case_id,
            "evidence_id": item.evidence_id,
            "file_name": item.file_name,
            "distance": distance,
            "similarity": similarity,
            "match_level": match_level,
            "pdf_report": item.pdf_report,
            "json_report": item.json_report,
        })

    matches.sort(key=lambda x: x["distance"])
    return matches