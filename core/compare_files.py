import json
import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

try:
    from skimage.metrics import structural_similarity as skimage_ssim
except ImportError:
    skimage_ssim = None

try:
    from core.image_diff import generate_diff_outputs
except ImportError:
    generate_diff_outputs = None

try:
    from core.comparison_pdf import generate_comparison_pdf
except ImportError:
    generate_comparison_pdf = None

from app.utils.hash_utils import sha256_file
from app.utils.metadata_utils import get_image_metadata, extract_exif
from app.utils.image_fingerprint import generate_phash


REPORT_LIMITATIONS_TEXT = (
    "This report reflects a tool-assisted forensic comparison of the files submitted for analysis. "
    "It does not independently establish authorship, ownership, date of creation, or legal infringement. "
    "Metadata and EXIF values may be absent, modified, or stripped during export, upload, screenshotting, "
    "platform processing, or editing. The conclusions stated herein are limited to the files reviewed "
    "and the indicators observable from those files."
)


def build_forensic_conclusion(
    sha256_match,
    phash_distance,
    ssim_score,
    metadata_diff_count=0,
    exif_diff_count=0,
    visual_assessment=None,
):
    if sha256_match:
        return {
            "confidence_level": "Exact File Match",
            "conclusion_title": "Exact Digital Match",
            "conclusion_text": (
                "The submitted file and the reference file are an exact digital match. "
                "The SHA-256 hash values are identical, which indicates that the files "
                "are byte-for-byte the same."
            ),
            "interpretation_text": (
                "This assessment is based primarily on identical cryptographic hash values, "
                "which establish file-level identity."
            ),
        }

    phash_distance = phash_distance if phash_distance is not None else 999
    ssim_score = ssim_score if ssim_score is not None else 0.0
    visual_assessment = (visual_assessment or "").lower()

    strong_visual = any(
        phrase in visual_assessment
        for phrase in [
            "high similarity",
            "very similar",
            "strong correspondence",
            "minimal visual differences",
        ]
    )

    moderate_visual = any(
        phrase in visual_assessment
        for phrase in [
            "moderate similarity",
            "notable but limited differences",
            "generally consistent",
        ]
    )

    if (ssim_score >= 0.90 and phash_distance <= 8) or (ssim_score >= 0.88 and strong_visual):
        return {
            "confidence_level": "High Confidence Match",
            "conclusion_title": "High Confidence Match",
            "conclusion_text": (
                "The submitted image exhibits a high degree of similarity to the reference image. "
                "The combined results of perceptual hash comparison, structural similarity analysis, "
                "and visual differential review support the conclusion that the submitted image is "
                "highly consistent with the reference image or a version derived from it. "
                "Observed differences, if any, are consistent with resizing, compression, cropping, "
                "or minor post-processing."
            ),
            "interpretation_text": (
                "This assessment is based on a combination of file-level, image-level, and visual "
                "comparison indicators, including perceptual hash similarity, structural similarity "
                "measurements, metadata review, EXIF review where available, and visual differential outputs. "
                "No single metric is determinative in isolation; the conclusion reflects the combined "
                "weight of the observed indicators."
            ),
        }

    if (ssim_score >= 0.75 and phash_distance <= 14) or moderate_visual:
        return {
            "confidence_level": "Probable Match",
            "conclusion_title": "Probable Match",
            "conclusion_text": (
                "The submitted image exhibits substantial similarity to the reference image. "
                "The comparison metrics and visual review support the opinion that the images "
                "are probably related, although the observed differences suggest editing, "
                "recompression, partial cropping, or other modification. This result is "
                "consistent with likely derivation, but not an exact file match."
            ),
            "interpretation_text": (
                "The available indicators support a meaningful relationship between the compared images, "
                "but the differences observed prevent classification as an exact digital match."
            ),
        }

    if ssim_score >= 0.60 and phash_distance <= 20:
        return {
            "confidence_level": "Inconclusive",
            "conclusion_title": "Inconclusive Result",
            "conclusion_text": (
                "The comparison produced mixed indicators. Certain metrics suggest similarity, "
                "but the available data does not support a reliable forensic conclusion that the "
                "submitted image is the same as, or derived from, the reference image. Additional "
                "contextual information, source files, or expert review may be necessary."
            ),
            "interpretation_text": (
                "Some indicators point toward similarity, but the overall evidentiary signal is not "
                "strong enough to support a higher-confidence conclusion."
            ),
        }

    return {
        "confidence_level": "No Significant Support for a Match",
        "conclusion_title": "No Significant Support for a Match",
        "conclusion_text": (
            "The comparison did not reveal sufficient forensic support for a meaningful match "
            "between the submitted image and the reference image. Based on the available metrics "
            "and visual differential review, the images do not appear to be materially consistent "
            "with one another."
        ),
        "interpretation_text": (
            "The observed indicators do not collectively support a reliable conclusion that the "
            "submitted image matches or was derived from the reference image."
        ),
    }


def _safe_relpath(path_value):
    if not path_value:
        return None
    return str(path_value).replace("\\", "/")


def _ensure_dir(path_value):
    os.makedirs(path_value, exist_ok=True)
    return path_value


def _load_image_rgb(path_value):
    with Image.open(path_value) as img:
        return img.convert("RGB")


def _load_image_gray(path_value, size=(1000, 1000)):
    with Image.open(path_value) as img:
        return img.convert("L").resize(size)


def _compute_ssim(original_path, suspect_path):
    img1 = _load_image_gray(original_path)
    img2 = _load_image_gray(suspect_path)

    if skimage_ssim is None:
        diff = ImageChops.difference(img1, img2)
        bbox = diff.getbbox()
        if bbox is None:
            return 1.0
        diff_pixels = sum(1 for value in diff.getdata() if value != 0)
        total_pixels = img1.size[0] * img1.size[1]
        return max(0.0, 1.0 - (diff_pixels / total_pixels))

    img1_array = __import__("numpy").array(img1)
    img2_array = __import__("numpy").array(img2)
    score = skimage_ssim(img1_array, img2_array)
    return float(score)


def _build_simple_diff_image(original_path, suspect_path, output_dir):
    original = _load_image_rgb(original_path)
    suspect = _load_image_rgb(suspect_path).resize(original.size)

    diff = ImageChops.difference(original, suspect)
    bbox = diff.getbbox()

    marked_original = original.copy()
    marked_suspect = suspect.copy()

    if bbox:
        draw_original = ImageDraw.Draw(marked_original)
        draw_suspect = ImageDraw.Draw(marked_suspect)
        draw_original.rectangle(bbox, outline="red", width=4)
        draw_suspect.rectangle(bbox, outline="red", width=4)

    difference_image_path = os.path.join(output_dir, "difference_map.png")
    marked_original_path = os.path.join(output_dir, "marked_original.png")
    marked_suspect_path = os.path.join(output_dir, "marked_suspect.png")
    side_by_side_path = os.path.join(output_dir, "side_by_side.png")

    diff.save(difference_image_path)
    marked_original.save(marked_original_path)
    marked_suspect.save(marked_suspect_path)

    side_by_side = Image.new("RGB", (original.width + suspect.width, max(original.height, suspect.height)))
    side_by_side.paste(original, (0, 0))
    side_by_side.paste(suspect, (original.width, 0))
    side_by_side.save(side_by_side_path)

    return {
        "difference_image": _safe_relpath(difference_image_path),
        "marked_original": _safe_relpath(marked_original_path),
        "marked_suspect": _safe_relpath(marked_suspect_path),
        "side_by_side": _safe_relpath(side_by_side_path),
    }


def _compare_dicts(left_dict, right_dict):
    left_dict = left_dict or {}
    right_dict = right_dict or {}
    diffs = []

    all_keys = sorted(set(left_dict.keys()) | set(right_dict.keys()))
    for key in all_keys:
        left_value = left_dict.get(key)
        right_value = right_dict.get(key)
        if left_value != right_value:
            diffs.append(
                {
                    "field": key,
                    "original": left_value,
                    "suspect": right_value,
                }
            )
    return diffs


def _visual_assessment(ssim_score, phash_distance):
    if ssim_score >= 0.90 and phash_distance <= 8:
        return "High similarity with minimal visual differences."
    if ssim_score >= 0.75 and phash_distance <= 14:
        return "Moderate to strong similarity with some visible differences."
    if ssim_score >= 0.60 and phash_distance <= 20:
        return "Mixed indicators with notable visual differences."
    return "Low similarity with substantial visual differences."


def _match_level(phash_distance, ssim_score):
    if ssim_score >= 0.90 and phash_distance <= 8:
        return "High"
    if ssim_score >= 0.75 and phash_distance <= 14:
        return "Moderate"
    if ssim_score >= 0.60 and phash_distance <= 20:
        return "Low"
    return "Minimal"


def _comparison_output_dir(case_path=None):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if case_path:
        return _ensure_dir(os.path.join(case_path, "comparisons", timestamp))
    return _ensure_dir(os.path.join("reports", "comparisons", timestamp))


def _build_pdf_differences(result, max_items=8):
    difference_lines = []

    if not result.get("sha256_match"):
        difference_lines.append("The files are not exact binary duplicates based on SHA-256 comparison.")

    for d in result.get("metadata_differences", [])[:max_items]:
        difference_lines.append(
            f"Metadata difference — {d.get('field')}: {d.get('original')} → {d.get('suspect')}"
        )

    remaining_slots = max(0, max_items - len(result.get("metadata_differences", [])[:max_items]))
    if remaining_slots > 0:
        for d in result.get("exif_differences", [])[:remaining_slots]:
            difference_lines.append(
                f"EXIF difference — {d.get('field')}: {d.get('original')} → {d.get('suspect')}"
            )

    if not difference_lines:
        difference_lines.append(
            "No significant distinguishing differences were recorded beyond those consistent with possible recompression, resizing, cropping, or metadata variation."
        )

    return difference_lines


def _build_pdf_payload(result):
    return {
        "suspect_file": result.get("suspect_file"),
        "reference_file": result.get("original_file"),
        "suspect_hash": result.get("suspect_sha256"),
        "reference_hash": result.get("original_sha256"),
        "suspect_phash": result.get("suspect_phash"),
        "reference_phash": result.get("original_phash"),
        "similarity_score": result.get("similarity_score"),
        "classification": result.get("confidence_level"),
        "phash_distance": result.get("phash_distance"),
        "sha256_match": result.get("sha256_match"),
        "differences": _build_pdf_differences(result),
        "analysis_date": result.get("generated_at"),
    }

def compare_two_files(original_path, suspect_path, case_path=None, original_filename=None, suspect_filename=None):
    original_path = str(original_path)
    suspect_path = str(suspect_path)

    output_dir = _comparison_output_dir(case_path)

    original_sha256 = sha256_file(original_path)
    suspect_sha256 = sha256_file(suspect_path)
    sha_match = original_sha256 == suspect_sha256

    original_phash = generate_phash(original_path)
    suspect_phash = generate_phash(suspect_path)

    try:
        import imagehash
        phash_distance = int(imagehash.hex_to_hash(original_phash) - imagehash.hex_to_hash(suspect_phash))
    except Exception:
        phash_distance = 999 if original_phash != suspect_phash else 0

    original_metadata = get_image_metadata(original_path)
    suspect_metadata = get_image_metadata(suspect_path)

    original_exif = extract_exif(original_path)
    suspect_exif = extract_exif(suspect_path)

    metadata_differences = _compare_dicts(original_metadata, suspect_metadata)
    exif_differences = _compare_dicts(original_exif, suspect_exif)

    try:
        ssim_score = _compute_ssim(original_path, suspect_path)
    except Exception:
        ssim_score = 0.0

    visual_summary = _visual_assessment(ssim_score, phash_distance)
    match_level = _match_level(phash_distance, ssim_score)

    diff_outputs = {}
    try:
        if generate_diff_outputs:
            generated = generate_diff_outputs(original_path, suspect_path, output_dir)
            if isinstance(generated, dict):
                diff_outputs = {k: _safe_relpath(v) for k, v in generated.items()}
        if not diff_outputs:
            diff_outputs = _build_simple_diff_image(original_path, suspect_path, output_dir)
    except Exception:
        diff_outputs = {}

    conclusion = build_forensic_conclusion(
        sha256_match=sha_match,
        phash_distance=phash_distance,
        ssim_score=ssim_score,
        metadata_diff_count=len(metadata_differences),
        exif_diff_count=len(exif_differences),
        visual_assessment=visual_summary,
    )

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "original_file": original_filename or os.path.basename(original_path),
        "suspect_file": suspect_filename or os.path.basename(suspect_path),
        "original_path": _safe_relpath(original_path),
        "suspect_path": _safe_relpath(suspect_path),
        "sha256_match": sha_match,
        "original_sha256": original_sha256,
        "suspect_sha256": suspect_sha256,
        "original_phash": str(original_phash),
        "suspect_phash": str(suspect_phash),
        "phash_distance": phash_distance,
        "ssim_score": round(float(ssim_score), 4),
        "similarity_score": round(float(ssim_score) * 100, 2),
        "match_level": match_level,
        "visual_assessment": visual_summary,
        "metadata_differences": metadata_differences,
        "exif_differences": exif_differences,
        "diff_outputs": diff_outputs,
        "difference_image": diff_outputs.get("difference_image"),
        "conclusion_title": conclusion["conclusion_title"],
        "confidence_level": conclusion["confidence_level"],
        "conclusion_text": conclusion["conclusion_text"],
        "interpretation_text": conclusion["interpretation_text"],
        "limitations_text": REPORT_LIMITATIONS_TEXT,
    }

    comparison_json_path = os.path.join(output_dir, "comparison_result.json")
    with open(comparison_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    comparison_pdf_path = os.path.join(output_dir, "comparison_report.pdf")
    if generate_comparison_pdf:
        try:
            pdf_payload = _build_pdf_payload(result)
            generate_comparison_pdf(pdf_payload, comparison_pdf_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            comparison_pdf_path = None

        except Exception:
            comparison_pdf_path = None
    else:
        comparison_pdf_path = None

    result["comparison_json"] = _safe_relpath(comparison_json_path)

    if comparison_pdf_path and os.path.exists(comparison_pdf_path):
        try:
            from app.storage import s3_client, AWS_S3_BUCKET, AWS_REGION
            s3_key = f"comparison_reports/{os.path.basename(output_dir)}_{os.path.basename(comparison_pdf_path)}"
            with open(comparison_pdf_path, "rb") as pdf_file:
                s3_client.upload_fileobj(pdf_file, AWS_S3_BUCKET, s3_key, ExtraArgs={"ContentType": "application/pdf"})
            s3_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": AWS_S3_BUCKET, "Key": s3_key},
                ExpiresIn=3600,
            )
            result["comparison_pdf"] = s3_url

        except Exception:
            result["comparison_pdf"] = _safe_relpath(comparison_pdf_path)
    else:
        result["comparison_pdf"] = None

    return result


def _find_case_path(case_id_or_path):
    candidate = Path(case_id_or_path)
    if candidate.exists():
        return str(candidate)
    return os.path.join("cases", str(case_id_or_path))


def _case_report_files(case_path):
    reports_dir = os.path.join(case_path, "reports")
    if not os.path.isdir(reports_dir):
        return []

    matches = []
    for root, _, files in os.walk(reports_dir):
        for filename in files:
            if filename == "analysis_report.json":
                matches.append(os.path.join(root, filename))
    return sorted(matches)


def _find_uploaded_evidence_file(case_path, file_name):
    uploads_dir = os.path.join(case_path, "uploads")
    if not os.path.isdir(uploads_dir):
        return None

    for root, _, files in os.walk(uploads_dir):
        for filename in files:
            if filename == file_name:
                return os.path.join(root, filename)
    return None

def compare_against_case(suspect_path, case_id_or_path):
    from app.utils.image_fingerprint import generate_phash
    from app.utils.hash_compare import hamming_distance
    from core.fingerprint_index import search_similar
    from app.db import SessionLocal
    from app.models import EvidenceItem
    from app.storage import download_to_tempfile

    case_id = os.path.basename(str(case_id_or_path))

    suspect_phash = generate_phash(suspect_path)

    all_matches = search_similar(
        suspect_phash,
        hamming_distance,
        max_distance=16,
    )

    case_matches = [m for m in all_matches if m.get("case_id") == case_id]

    matches = []
    best_match = None

    for match in case_matches:
        db = SessionLocal()
        try:
            item = db.query(EvidenceItem).filter(
                EvidenceItem.case_id == case_id,
                EvidenceItem.evidence_id == match.get("evidence_id"),
            ).first()
        finally:
            db.close()

        if not item or not item.file_key:
            continue

        suffix = os.path.splitext(item.file_name)[1]
        evidence_path = download_to_tempfile(item.file_key, suffix=suffix)

        try:
            comparison = compare_two_files(evidence_path, suspect_path,
                original_filename=item.file_name,
                suspect_filename=os.path.basename(str(suspect_path)),
)

            comparison["case_id"] = case_id
            comparison["evidence_id"] = item.evidence_id
            comparison["reference_file"] = item.file_name
            matches.append(comparison)
        finally:
            os.remove(evidence_path)

    matches.sort(
        key=lambda item: (
            -item.get("similarity_score", 0),
            item.get("phash_distance", 999),
        )
    )

    if matches:
        best_match = matches[0]

    return {
        "case_id": case_id,
        "suspect_file": os.path.basename(str(suspect_path)),
        "suspect_phash": suspect_phash,
        "best_match": best_match,
        "matches": matches,
        "match_count": len(matches),
    }

def compare_against_all_cases(suspect_path, cases_root="cases"):
    cases_root = str(cases_root)
    all_results = []
    all_matches = []

    if not os.path.isdir(cases_root):
        return {
            "suspect_file": os.path.basename(str(suspect_path)),
            "best_match": None,
            "cases_reviewed": 0,
            "matches": [],
        }

    for entry in os.listdir(cases_root):
        case_path = os.path.join(cases_root, entry)
        if not os.path.isdir(case_path):
            continue

        case_result = compare_against_case(suspect_path, case_path)
        all_results.append(case_result)
        all_matches.extend(case_result.get("matches", []))

    all_matches.sort(
        key=lambda item: (
            -item.get("similarity_score", 0),
            item.get("phash_distance", 999),
        )
    )

    best_match = all_matches[0] if all_matches else None

    return {
        "suspect_file": os.path.basename(str(suspect_path)),
        "best_match": best_match,
        "cases_reviewed": len(all_results),
        "matches": all_matches[:25],
        "case_results": all_results,
    }