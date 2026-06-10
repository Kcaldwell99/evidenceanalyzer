import hashlib
from app.storage import get_file


def sha256_from_storage(file_key):
    """
    Re-fetch a stored object by its key and recompute its SHA-256.
    Returns the hex digest, or None if the object is missing/unreadable.
    """
    if not file_key:
        return None
    try:
        data = get_file(file_key)
    except Exception:
        return None
    sha256 = hashlib.sha256()
    mv = memoryview(data)
    for i in range(0, len(mv), 4096):
        sha256.update(mv[i:i + 4096])
    return sha256.hexdigest()


def verify_integrity(stored_sha256, file_key):
    """
    Recompute the stored file's hash and compare to the value recorded at upload.
    3-state result:
        {"recomputed": <hex>, "match": True}   re-verification succeeded, hashes equal
        {"recomputed": <hex>, "match": False}  hashes differ — tamper signal
        {"recomputed": None,  "match": None}   object unavailable — could not re-verify
    """
    recomputed = sha256_from_storage(file_key)
    if recomputed is None:
        return {"recomputed": None, "match": None}
    if not stored_sha256 or stored_sha256 == "—":
        return {"recomputed": recomputed, "match": None}
    return {"recomputed": recomputed, "match": recomputed == stored_sha256}
