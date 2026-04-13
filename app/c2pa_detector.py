import json

try:
    import c2pa
    C2PA_AVAILABLE = True
except ImportError:
    C2PA_AVAILABLE = False


def read_c2pa_manifest(file_path: str) -> dict:
    result = {
        "has_manifest": False,
        "verified": False,
        "manifest_data": None,
        "flagged_ai": False,
        "flagged_no_credentials": False,
        "error": None,
    }

    if not C2PA_AVAILABLE:
        result["error"] = "c2pa-python library not installed."
        return result

    try:
        reader = c2pa.Reader.from_file(file_path)
        manifest_json = reader.json()
        manifest_data = json.loads(manifest_json)

        result["has_manifest"] = True
        result["manifest_data"] = manifest_data

        manifests = manifest_data.get("manifests", {})
        for manifest_key, manifest in manifests.items():
            assertions = manifest.get("assertions", [])
            for assertion in assertions:
                label = assertion.get("label", "").lower()
                data = assertion.get("data", {})
                if "ai.generated" in label or "ai_generated" in label:
                    result["flagged_ai"] = True
                if "training-mining" in label:
                    result["flagged_ai"] = True
                actions = data.get("actions", [])
                for action in actions:
                    if "ai" in action.get("softwareAgent", "").lower():
                        result["flagged_ai"] = True

        result["verified"] = True

    except Exception as e:
        err = str(e).lower()
        if "no manifest" in err or "not found" in err or "missing" in err:
            result["has_manifest"] = False
            result["flagged_no_credentials"] = True
        else:
            result["error"] = str(e)

    return result


def summarize_c2pa(result: dict) -> str:
    if not C2PA_AVAILABLE:
        return "C2PA detection unavailable."

    if result.get("error"):
        return f"C2PA check encountered an error: {result['error']}"

    if not result.get("has_manifest"):
        return (
            "No C2PA Content Credentials manifest was detected in this file. "
            "The absence of credentials does not confirm manipulation, but the file "
            "cannot be verified as originating from a credentialed capture device or software."
        )

    summary = "C2PA Content Credentials manifest detected and read successfully."

    if result.get("flagged_ai"):
        summary += (
            " The manifest contains assertions consistent with AI-generated or "
            "AI-modified content. This file should be treated with heightened scrutiny."
        )
    else:
        summary += " No AI-generation assertions were identified in the manifest."

    return summary