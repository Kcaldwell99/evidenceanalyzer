def check_c2pa_presence(path):
    filename = str(path).lower()

    return {
        "has_c2pa": "c2pa" in filename,
        "validation_status": "unknown",
        "notes": "Placeholder detector only."
    }