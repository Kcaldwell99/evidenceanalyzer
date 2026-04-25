"""
app/c2pa_analysis.py

Full C2PA analysis module for Evidentix.
Replaces: app/c2pa_detector.py, app/utils/c2pa_utils.py, core/c2pa_check.py

Provides:
  - analyze_file(file_path)  → C2PAResult (full structured result)
  - summarize_for_certificate(result) → dict  (Section 3 of Integrity Certificate)
  - plain_english_findings(result) → str  (judge-readable narrative)

Three-state model:
  VALID   — manifest present, signature verified, issuer trusted, not revoked
  INVALID — manifest present but signature bad, issuer untrusted, or revoked
  ABSENT  — no manifest embedded in file
"""

import json
import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# ---------------------------------------------------------------------------
# Optional dependency guard
# ---------------------------------------------------------------------------
try:
    import c2pa
    C2PA_AVAILABLE = True
except ImportError:
    C2PA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------

class C2PAState(str, Enum):
    VALID   = "VALID"
    INVALID = "INVALID"
    ABSENT  = "ABSENT"
    UNAVAILABLE = "UNAVAILABLE"   # library not installed


# Assertion labels that indicate AI generation or AI modification
AI_GENERATION_LABELS = {
    "ai.generated",
    "ai_generated",
    "com.adobe.ai-generated",
}

AI_MODIFICATION_LABELS = {
    "com.adobe.generative-fill",
    "com.adobe.firefly",
    "c2pa.ai_inferencing",
}

TRAINING_MINING_LABELS = {
    "c2pa.training-mining",
    "org.contentauthenticity.training-mining",
}

# Known software agents that indicate AI tooling
AI_SOFTWARE_AGENTS = {
    "dall-e", "midjourney", "stable diffusion", "firefly",
    "generative fill", "ai", "gpt", "imagen", "gemini",
}

# Assertion labels that represent editorial/creative actions
CREATIVE_ACTION_LABELS = {
    "c2pa.cropped", "c2pa.resized", "c2pa.color_adjustments",
    "c2pa.converted", "c2pa.filtered", "c2pa.edited",
    "c2pa.color_space_converted", "c2pa.drawing",
    "c2pa.repackaged", "c2pa.transcoded",
}

# Assertion labels we surface explicitly in findings
PROVENANCE_LABELS = {
    "c2pa.hash.data",
    "c2pa.hash.blocks",
    "c2pa.thumbnail.claim.jpeg",
    "c2pa.thumbnail.claim.png",
    "c2pa.location",
    "c2pa.exif",
    "stds.exif",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class C2PAResult:
    # Top-level state
    state: C2PAState = C2PAState.UNAVAILABLE
    analyzed_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    # Manifest metadata
    active_manifest_label: Optional[str] = None
    claim_generator: Optional[str] = None      # software that created the manifest
    claim_generator_version: Optional[str] = None
    num_manifests: int = 0

    # Signature & trust
    signature_valid: Optional[bool] = None
    signature_issuer: Optional[str] = None
    signature_time: Optional[str] = None
    trust_list_status: Optional[str] = None    # "trusted" | "untrusted" | "unknown"
    revocation_status: Optional[str] = None    # "not_revoked" | "revoked" | "unknown"

    # Assertions
    has_ai_generation: bool = False
    has_ai_modification: bool = False
    has_training_mining: bool = False
    training_mining_allowed: Optional[bool] = None
    creative_actions: list = field(default_factory=list)
    provenance_assertions: list = field(default_factory=list)
    all_assertion_labels: list = field(default_factory=list)

    # AI software agents found
    ai_agents_found: list = field(default_factory=list)

    # Ingredients (parent files this was derived from)
    ingredients: list = field(default_factory=list)

    # Raw manifest for downstream use
    raw_manifest: Optional[dict] = None

    # Error detail (if state == INVALID due to parse/verify error)
    error_detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_file(file_path: str) -> C2PAResult:
    """
    Primary entry point. Returns a fully populated C2PAResult.
    Never raises — errors are captured in result.error_detail.
    """
    result = C2PAResult()

    if not C2PA_AVAILABLE:
        result.state = C2PAState.UNAVAILABLE
        result.error_detail = "c2pa-python library is not installed."
        return result

    try:
        ext = str(file_path).lower().rsplit(".", 1)[-1]
        mime = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp","mp4":"video/mp4","mov":"video/quicktime","pdf":"application/pdf"}.get(ext, "application/octet-stream")
        with open(file_path, "rb") as f:
            with c2pa.Reader(mime, f) as reader:
                raw_json = reader.json()
        manifest_data = json.loads(raw_json)
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ("no manifest", "not found", "missing", "no active manifest", "no claim", "does not contain", "jumbf", "manifestnotfound")):
            result.state = C2PAState.ABSENT
        else:
            result.state = C2PAState.INVALID
            result.error_detail = f"Failed to read C2PA manifest: {str(e)}"
        return result

    result.raw_manifest = manifest_data
    manifests = manifest_data.get("manifests", {})
    result.num_manifests = len(manifests)
    result.active_manifest_label = manifest_data.get("active_manifest")

    if result.num_manifests == 0 or not result.active_manifest_label:
        result.state = C2PAState.ABSENT
        return result

    # Pull the active manifest
    active = manifests.get(result.active_manifest_label, {})

    # Claim generator
    cg = active.get("claim_generator", "")
    if "/" in cg:
        parts = cg.split("/", 1)
        result.claim_generator = parts[0].strip()
        result.claim_generator_version = parts[1].strip()
    else:
        result.claim_generator = cg

    # Signature info
    sig = active.get("signature_info", {})
    result.signature_issuer = sig.get("issuer") or sig.get("cert_serial_number")
    result.signature_time = sig.get("time")

    # Validation status from reader
    try:
        validation = manifest_data.get("validation_status", [])
        _parse_validation_status(result, validation)
    except Exception:
        result.signature_valid = None
        result.trust_list_status = "unknown"
        result.revocation_status = "unknown"

    # Parse assertions
    assertions = active.get("assertions", [])
    _parse_assertions(result, assertions)

    # Parse ingredients
    ingredients = active.get("ingredients", [])
    _parse_ingredients(result, ingredients)

    # Determine final state
    result.state = _determine_state(result)

    return result


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _parse_validation_status(result: C2PAResult, validation: list):
    """
    Interprets the validation_status array from the C2PA reader.
    The c2pa-python library returns a list of status objects with 'code' fields.
    """
    if not validation:
        # No validation entries = library did not flag anything = treat as valid
        result.signature_valid = True
        result.trust_list_status = "unknown"
        result.revocation_status = "unknown"
        return

    error_codes = {str(v.get("code", "")).lower() for v in validation if isinstance(v, dict)}

    # Signature validity
    sig_errors = {c for c in error_codes if "signature" in c or "cert" in c or "hash" in c}
    result.signature_valid = len(sig_errors) == 0

    # Trust list
    if any("trust" in c for c in error_codes):
        result.trust_list_status = "untrusted"
    elif any("ocsp" in c or "revok" in c or "crl" in c for c in error_codes):
        result.revocation_status = "revoked"
        result.trust_list_status = "unknown"
    else:
        result.trust_list_status = "trusted" if result.signature_valid else "unknown"

    # Revocation
    if any("revok" in c or "ocsp" in c or "crl" in c for c in error_codes):
        result.revocation_status = "revoked"
    else:
        result.revocation_status = "not_revoked"


def _parse_assertions(result: C2PAResult, assertions: list):
    """Walk every assertion and populate result fields."""
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue

        label = assertion.get("label", "").lower()
        data = assertion.get("data", {}) or {}

        result.all_assertion_labels.append(label)

        # AI generation
        if any(ai in label for ai in AI_GENERATION_LABELS):
            result.has_ai_generation = True

        # AI modification
        if any(ai in label for ai in AI_MODIFICATION_LABELS):
            result.has_ai_modification = True

        # Training/mining
        if any(t in label for t in TRAINING_MINING_LABELS):
            result.has_training_mining = True
            # Try to read the allowed flag
            if isinstance(data, dict):
                entries = data.get("entries", [])
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict) and "allowed" in entry:
                            result.training_mining_allowed = entry["allowed"]
                            break

        # Creative actions
        if any(label.startswith(ca) for ca in CREATIVE_ACTION_LABELS):
            result.creative_actions.append(label)

        # Provenance
        if any(label.startswith(pl) for pl in PROVENANCE_LABELS):
            result.provenance_assertions.append(label)

        # AI software agents in action assertions
        actions = data.get("actions", []) if isinstance(data, dict) else []
        if isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict):
                    continue
                agent = action.get("softwareAgent", "").lower()
                for known_agent in AI_SOFTWARE_AGENTS:
                    if known_agent in agent and agent not in result.ai_agents_found:
                        result.ai_agents_found.append(agent)
                        result.has_ai_modification = True


def _parse_ingredients(result: C2PAResult, ingredients: list):
    """Extract ingredient summary (parent files this was derived from)."""
    for ing in ingredients:
        if not isinstance(ing, dict):
            continue
        entry = {
            "title": ing.get("title"),
            "format": ing.get("format"),
            "relationship": ing.get("relationship"),
            "has_manifest": bool(ing.get("active_manifest")),
        }
        result.ingredients.append(entry)


def _determine_state(result: C2PAResult) -> C2PAState:
    """
    Final state decision tree.
    VALID   = has manifest AND (signature valid or unknown) AND not revoked
    INVALID = has manifest AND (signature invalid OR revoked OR untrusted)
    ABSENT  = no manifest
    """
    if result.num_manifests == 0:
        return C2PAState.ABSENT

    if result.revocation_status == "revoked":
        return C2PAState.INVALID

    if result.signature_valid is False:
        return C2PAState.INVALID

    if result.trust_list_status == "untrusted":
        return C2PAState.INVALID

    return C2PAState.VALID


# ---------------------------------------------------------------------------
# Certificate Section 3 output
# ---------------------------------------------------------------------------

def summarize_for_certificate(result: C2PAResult) -> dict:
    """
    Returns a structured dict for Section 3 of the Integrity Certificate.
    Keys map directly to PDF template placeholders.
    """
    return {
        "state": result.state.value,
        "state_label": _state_label(result.state),
        "analyzed_at": result.analyzed_at,
        "claim_generator": result.claim_generator,
        "claim_generator_version": result.claim_generator_version,
        "signature_issuer": result.signature_issuer,
        "signature_time": result.signature_time,
        "signature_valid": result.signature_valid,
        "trust_list_status": result.trust_list_status,
        "revocation_status": result.revocation_status,
        "has_ai_generation": result.has_ai_generation,
        "has_ai_modification": result.has_ai_modification,
        "has_training_mining": result.has_training_mining,
        "training_mining_allowed": result.training_mining_allowed,
        "creative_actions": result.creative_actions,
        "ai_agents_found": result.ai_agents_found,
        "num_ingredients": len(result.ingredients),
        "num_assertions": len(result.all_assertion_labels),
        "plain_english": plain_english_findings(result),
        "error_detail": result.error_detail,
    }


def _state_label(state: C2PAState) -> str:
    return {
        C2PAState.VALID:       "Content Credentials Present and Verified",
        C2PAState.INVALID:     "Content Credentials Present — Verification Failed",
        C2PAState.ABSENT:      "No Content Credentials Detected",
        C2PAState.UNAVAILABLE: "C2PA Analysis Unavailable",
    }[state]


# ---------------------------------------------------------------------------
# Judge-readable plain English narrative
# ---------------------------------------------------------------------------

def plain_english_findings(result: C2PAResult) -> str:
    """
    Returns a plain-English paragraph suitable for a legal report or
    certificate narrative. Written to be understood by a judge or jury
    without technical background.
    """
    if result.state == C2PAState.UNAVAILABLE:
        return (
            "Content Credentials analysis could not be performed because the "
            "required analysis library is not available on this system."
        )

    if result.state == C2PAState.ABSENT:
        return (
            "This file does not contain embedded Content Credentials (C2PA provenance data). "
            "The absence of Content Credentials does not by itself establish that this file "
            "was altered or fabricated; many legitimate files are created by software that "
            "does not embed this standard. However, the file's origin, authorship, and editing "
            "history cannot be independently verified through the Content Credentials standard."
        )

    # Build narrative for VALID or INVALID
    lines = []

    # Opening: state
    if result.state == C2PAState.VALID:
        lines.append(
            "This file contains embedded Content Credentials (C2PA provenance data) that passed "
            "cryptographic verification. The digital signature attached to these credentials was "
            "confirmed as intact and unmodified."
        )
    else:
        lines.append(
            "This file contains embedded Content Credentials (C2PA provenance data), but one or "
            "more verification checks failed. The reasons are detailed below."
        )

    # Claim generator
    if result.claim_generator:
        ver = f" (version {result.claim_generator_version})" if result.claim_generator_version else ""
        lines.append(
            f"The credentials were created by {result.claim_generator}{ver}."
        )

    # Signature time
    if result.signature_time:
        lines.append(
            f"The manifest was digitally signed on {result.signature_time}."
        )

    # Issuer
    if result.signature_issuer:
        lines.append(
            f"The signing certificate was issued by: {result.signature_issuer}."
        )

    # Trust list
    if result.trust_list_status == "trusted":
        lines.append(
            "The signing certificate belongs to a recognized Content Credentials issuer."
        )
    elif result.trust_list_status == "untrusted":
        lines.append(
            "WARNING: The signing certificate was not found on the recognized Content Credentials "
            "Trust List. This means the identity of the party that signed these credentials "
            "cannot be independently confirmed."
        )

    # Revocation
    if result.revocation_status == "revoked":
        lines.append(
            "WARNING: The signing certificate has been revoked. A revoked certificate indicates "
            "that the issuing authority has withdrawn trust from the signer. Content Credentials "
            "signed with a revoked certificate cannot be considered reliable."
        )
    elif result.revocation_status == "not_revoked":
        lines.append(
            "The signing certificate has not been revoked."
        )

    # Signature validity (only surface if failed)
    if result.signature_valid is False:
        lines.append(
            "WARNING: The cryptographic signature did not validate. This means the file's "
            "Content Credentials may have been altered after they were originally embedded, "
            "or the file itself may have been modified."
        )

    # AI findings
    if result.has_ai_generation:
        lines.append(
            "The Content Credentials assert that this file was generated by artificial intelligence. "
            "This means the file's content was produced by an AI system, not captured by a camera "
            "or created directly by a human."
        )
    elif result.has_ai_modification:
        agents = ", ".join(result.ai_agents_found) if result.ai_agents_found else "an AI tool"
        lines.append(
            f"The Content Credentials indicate that portions of this file were modified using "
            f"AI-assisted tools ({agents}). The file may have been partially AI-generated or "
            f"edited with generative AI features."
        )
    else:
        lines.append(
            "No assertions of AI generation or AI modification were found in the Content Credentials."
        )

    # Training/mining
    if result.has_training_mining:
        if result.training_mining_allowed is True:
            lines.append(
                "The Content Credentials indicate the file's creator has explicitly permitted "
                "use of this content for AI training and data mining."
            )
        elif result.training_mining_allowed is False:
            lines.append(
                "The Content Credentials include an explicit assertion that this content may NOT "
                "be used for AI training or data mining."
            )
        else:
            lines.append(
                "The Content Credentials contain a training and data mining assertion, "
                "but the permitted/not-permitted status could not be determined."
            )

    # Creative actions
    if result.creative_actions:
        action_list = ", ".join(
            a.replace("c2pa.", "").replace("_", " ") for a in result.creative_actions
        )
        lines.append(
            f"The following editing operations were recorded in the Content Credentials: "
            f"{action_list}."
        )

    # Ingredients
    if result.ingredients:
        n = len(result.ingredients)
        lines.append(
            f"The Content Credentials identify {n} source file{'s' if n > 1 else ''} from which "
            f"this file was derived, indicating it was assembled or converted from prior material."
        )

    # Closing caveat
    if result.state == C2PAState.VALID:
        lines.append(
            "Content Credentials verification confirms the provenance record embedded in this file "
            "is authentic and has not been tampered with. It does not independently confirm the "
            "accuracy of the events or content depicted."
        )
    else:
        lines.append(
            "Because one or more verification checks failed, the Content Credentials embedded in "
            "this file should not be relied upon as evidence of authentic provenance without "
            "further investigation."
        )

    return " ".join(lines)


# ---------------------------------------------------------------------------
# Legacy compatibility shim
# (so existing imports of c2pa_detector don't break before we remove them)
# ---------------------------------------------------------------------------

def read_c2pa_manifest(file_path: str) -> dict:
    """
    Shim for backward compatibility with c2pa_detector.read_c2pa_manifest().
    Returns a dict shaped like the old output so nothing breaks during transition.
    """
    result = analyze_file(file_path)
    return {
        "has_manifest": result.state in (C2PAState.VALID, C2PAState.INVALID),
        "verified": result.state == C2PAState.VALID,
        "manifest_data": result.raw_manifest,
        "flagged_ai": result.has_ai_generation or result.has_ai_modification,
        "flagged_no_credentials": result.state == C2PAState.ABSENT,
        "error": result.error_detail,
        # Extended fields not in old shim
        "_c2pa_result": result,
    }


def summarize_c2pa(result_dict: dict) -> str:
    """
    Shim for backward compatibility with c2pa_detector.summarize_c2pa().
    Accepts the dict returned by read_c2pa_manifest().
    """
    c2pa_result = result_dict.get("_c2pa_result")
    if c2pa_result:
        return plain_english_findings(c2pa_result)

    # Fallback if called without the extended field
    if not C2PA_AVAILABLE:
        return "C2PA detection unavailable."
    if result_dict.get("error"):
        return f"C2PA check encountered an error: {result_dict['error']}"
    if not result_dict.get("has_manifest"):
        return (
            "Content Credentials not detected. This file does not contain embedded C2PA "
            "provenance data. The absence of Content Credentials does not confirm tampering, "
            "but the file's origin and editing history cannot be verified through this standard."
        )
    return "Content Credentials detected. See detailed findings."