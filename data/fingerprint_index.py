import json
import os

INDEX_PATH = os.path.join("data", "fingerprint_index.json")


def load_index():
    if not os.path.exists(INDEX_PATH):
        return []

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def add_fingerprint(case_id, evidence_id, file_name, phash, pdf_report=None, json_report=None):
    index = load_index()

    existing = next(
        (
            item for item in index
            if item.get("case_id") == case_id
            and item.get("evidence_id") == evidence_id
        ),
        None,
    )

    record = {
        "case_id": case_id,
        "evidence_id": evidence_id,
        "file_name": file_name,
        "phash": phash,
        "pdf_report": pdf_report,
        "json_report": json_report,
    }

    if existing:
        existing.update(record)
    else:
        index.append(record)

    save_index(index)


def search_similar(phash, distance_func, max_distance=8):
    index = load_index()
    matches = []

    for item in index:
        item_phash = item.get("phash")
        if not item_phash:
            continue

        distance = distance_func(phash, item_phash)
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
            "case_id": item.get("case_id"),
            "evidence_id": item.get("evidence_id"),
            "file_name": item.get("file_name"),
            "distance": distance,
            "similarity": similarity,
            "match_level": match_level,
            "pdf_report": item.get("pdf_report"),
            "json_report": item.get("json_report"),
        })

    matches.sort(key=lambda x: x["distance"])
    return matches