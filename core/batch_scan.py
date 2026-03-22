import os
from core.fingerprint_index import search_similar
from app.utils.image_fingerprint import generate_phash
from core.perceptual_hash import phash_distance as hamming_distance

def scan_folder(folder_path):

    results = []

    for file in os.listdir(folder_path):

        if not file.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue

        file_path = os.path.join(folder_path, file)

        phash = generate_phash(file_path)

        matches = search_similar(
            phash=phash,
            distance_func=hamming_distance,
            max_distance=12
        )

        if matches:
            results.append({
                "file": file,
                "matches": matches
            })

    return results