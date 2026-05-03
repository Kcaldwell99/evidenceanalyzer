import imagehash
from PIL import Image


def hash_frames(frame_paths):
    hashes = []
    for path in frame_paths:
        try:
            img = Image.open(path)
            phash = imagehash.phash(img)
            hashes.append({
                "path": path,
                "phash": str(phash),
            })
        except Exception:
            continue
    return hashes


def compare_frame_sets(set1, set2, max_distance=8):
    matches = []
    for f1 in set1:
        for f2 in set2:
            try:
                dist = (
                    imagehash.hex_to_hash(f1["phash"])
                    - imagehash.hex_to_hash(f2["phash"])
                )
                if dist <= max_distance:
                    matches.append({
                        "frame1": f1["path"],
                        "frame2": f2["path"],
                        "distance": dist,
                    })
            except Exception:
                continue
    return matches