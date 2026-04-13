import json
from pathlib import Path

try:
    import c2pa
    C2PA_AVAILABLE = True
except ImportError:
    C2PA_AVAILABLE = False


def read_c2pa_manifest(file_path: str) -> dict:
    """
    Attempts to read a C2PA manifest from the given file.
    Returns a dict with keys: has_manifest, verified, manifest_data, error, flagged_ai
    """
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

        # Check for AI-generated content assertions
        manifests = manifest_data.get("manifests", {})
        for manifest_key, manifest in manifests.items():
            assertions = manifest.get("assertions", [])
            for assertion in assertions:
                label = assertion.get("label", "").lower()
                data = assertion.get("data", {})

                # Flag AI-generated content
                if "ai.generated" in label or "ai_generated" in label:
                    result["flagged_ai"] = True

                if "training-mining" in label:
                    result["flagged_ai"] = True

                # Check actions for AI creation
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
    """Returns a plain-English summary for the forensic report."""
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
        summary += (
            " No AI-generation assertions were identified in the manifest."
        )

    return summary