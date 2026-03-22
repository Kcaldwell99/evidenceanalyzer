import json
import os

INDEX_PATH = os.path.join("data", "fingerprint_index.json")


def load_index():
    if not os.path.exists(INDEX_PATH):
        return []

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def add_fingerprint(case_id, evidence_id, file_name, phash):
    index = load_index()

    index.append({
        "case_id": case_id,
        "evidence_id": evidence_id,
        "file_name": file_name,
        "phash": phash
    })

    save_index(index)


def search_similar(phash, distance_func, max_distance=8):
    index = load_index()
    matches = []

    for item in index:
        distance = distance_func(phash, item["phash"])

        if distance <= max_distance:
            matches.append({
                "case_id": item["case_id"],
                "evidence_id": item["evidence_id"],
                "file_name": item["file_name"],
                "distance": distance
            })

    matches.sort(key=lambda x: x["distance"])

    return matches