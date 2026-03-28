import json
import os
import imagehash

from analyze_media import analyze_file
from core.perceptual_hash import get_phash
from core.image_diff import generate_diff_outputs
from core.comparison_pdf import generate_comparison_pdf


def compare_against_case(suspect_path, case_id):
    case_path = os.path.join("cases", case_id)
    evidence_index_path = os.path.join(case_path, "evidence_index.json")

    suspect_phash = get_phash(suspect_path)

    if not os.path.exists(evidence_index_path):
        return {
            "suspect_phash": suspect_phash,
            "comparison": None,
            "matches": []
        }

    with open(evidence_index_path, "r", encoding="utf-8") as f:
        evidence_items = json.load(f)

    matches = []

    for item in evidence_items:
        evidence_phash = item.get("phash")
        if not evidence_phash:
            continue
        distance = imagehash.hex_to_hash(suspect_phash) - imagehash.hex_to_hash(evidence_phash)
        similarity = max(0, round(100 - (distance * 100 / 64), 2))

        if distance <= 5:
            match_level = "High"
        elif distance <= 12:
            match_level = "Moderate"
        elif distance <= 20:
            match_level = "Low"
        else:
            match_level = "Minimal"

        matches.append({
            "evidence_id": item.get("evidence_id"),
            "file_name": item.get("file_name"),
            "distance": distance,
            "similarity": similarity,
            "match_level": match_level,
            "pdf_report": item.get("pdf_report"),
            "json_report": item.get("json_report"),
            "file_path": os.path.join(case_path, "uploads", item.get("file_name"))
        })

    matches.sort(key=lambda x: x["distance"])

    if not matches:
        return {
            "suspect_phash": suspect_phash,
            "comparison": None,
            "matches": []
        }

    best_match = matches[0]
    best_match_path = best_match["file_path"]

    comparison = compare_two_files(
        original_path=best_match_path,
        suspected_path=suspect_path,
        case_path=case_path
    )

    comparison["best_match_evidence_id"] = best_match["evidence_id"]
    comparison["best_match_distance"] = best_match["distance"]
    comparison["best_match_similarity"] = best_match["similarity"]
    comparison["best_match_level"] = best_match["match_level"]

    return {
        "suspect_phash": suspect_phash,
        "comparison": comparison,
        "matches": matches
    }

def compare_two_files(original_path: str, suspected_path: str, case_path: str) -> dict:
    print("COMPARE FUNCTION RUNNING")
    print("COMPARE_TWO_FILES FUNCTION EXECUTED")

    original_report, original_json, original_pdf = analyze_file(original_path, case_path)
    suspected_report, suspected_json, suspected_pdf = analyze_file(suspected_path, case_path)

    original_meta = original_report.get("image_metadata", {})
    suspected_meta = suspected_report.get("image_metadata", {})

    all_keys = sorted(set(original_meta.keys()) | set(suspected_meta.keys()))
    metadata_differences = []

for key in all_keys:
    original_value = original_meta.get(key)
    suspected_value = suspected_meta.get(key)

    if original_value != suspected_value:
        metadata_differences.append({
            "field": key,
            "original": original_value,
            "suspected": suspected_value,
        })
    original_exif = original_report.get("exif", {}) or {}
    suspected_exif = suspected_report.get("exif", {}) or {}

    exif_differences = []
    exif_keys = sorted(set(original_exif.keys()) | set(suspected_exif.keys()))

    for key in exif_keys:
        original_value = original_exif.get(key)
        suspected_value = suspected_exif.get(key)

        if original_value != suspected_value:
            exif_differences.append({
                "field": key,
                "original": original_value,
                "suspected": suspected_value,
            })

    original_phash = get_phash(original_path)
    suspected_phash = get_phash(suspected_path)

    distance = imagehash.hex_to_hash(original_phash) - imagehash.hex_to_hash(suspected_phash)
    similarity_score = max(0, round(100 - (distance * 100 / 64), 2))

    same_dimensions = (
        original_meta.get("width") == suspected_meta.get("width")
        and original_meta.get("height") == suspected_meta.get("height")
    )

    sha256_match = original_report.get("sha256") == suspected_report.get("sha256")
    similarity_percent = diff_result.get("similarity_percent", 0)

    if sha256_match:
        conclusion = "The files are byte-for-byte identical based on matching SHA256 hashes."
    elif similarity_percent >= 95:
        conclusion = "The files are not identical at the binary level, but visual comparison indicates they are highly similar."
    elif similarity_percent >= 80:
        conclusion = "The files are not identical, but visual comparison indicates moderate similarity consistent with possible editing, recompression, or derivation."
    elif same_dimensions:
        conclusion = "The files are not identical and show limited similarity, though they share the same image dimensions."
    else:
        conclusion = "The files are not identical and do not show strong similarity based on current hash, metadata, and visual comparison checks."

    comparison = {
        "original_file": original_report.get("file_name"),
        "suspected_file": suspected_report.get("file_name"),
        "original_file_path": "/" + original_path.replace("\\", "/"),
        "suspected_file_path": "/" + suspected_path.replace("\\", "/"),
        "original_sha256": original_report.get("sha256"),
        "suspected_sha256": suspected_report.get("sha256"),
        "sha256_match": sha256_match,
        "original_phash": original_phash,
        "suspected_phash": suspected_phash,
        "metadata_differences": metadata_differences,
        "exif_differences": exif_differences,
        "phash_distance": distance,
        "similarity_score": similarity_score,
        "original_size": original_report.get("size_bytes"),
        "suspected_size": suspected_report.get("size_bytes"),
        "same_size": original_report.get("size_bytes") == suspected_report.get("size_bytes"),
        "original_dimensions": (
            original_meta.get("width"),
            original_meta.get("height"),
        ),
        "suspected_dimensions": (
            suspected_meta.get("width"),
            suspected_meta.get("height"),
        ),
        "same_dimensions": same_dimensions,

        "conclusion": conclusion,
        "original_json": original_json,
        "original_pdf": original_pdf,
        "suspected_json": suspected_json,
        "suspected_pdf": suspected_pdf,
    }

    report_dir = os.path.dirname(original_pdf)

    diff_result = generate_diff_outputs(
        image_path_a=original_path,
        image_path_b=suspected_path,
        output_dir=report_dir,
    )

    comparison.update({
        "ssim_score": diff_result["ssim_score"],
        "similarity_percent": diff_result["similarity_percent"],
        "visual_assessment": diff_result["visual_assessment"],
        "difference_regions": diff_result["difference_regions"],
        "side_by_side_path": diff_result["side_by_side_path"],
        "heatmap_path": diff_result["heatmap_path"],
        "original_marked_path": diff_result["original_marked_path"],
        "suspect_marked_path": diff_result["suspect_marked_path"],
        "normalized_original_path": diff_result.get("normalized_original_path"),
        "normalized_suspect_path": diff_result.get("normalized_suspect_path"),
        "diff_map_path": diff_result.get("diff_map_path"),
        "threshold_map_path": diff_result.get("threshold_map_path"),
    })

    comparison_pdf_path = os.path.join(report_dir, "comparison_report.pdf")
    generate_comparison_pdf(comparison, comparison_pdf_path)
    comparison["comparison_pdf"] = comparison_pdf_path

    print("DEBUG similarity_score =", similarity_score)
    print("DEBUG comparison keys =", comparison.keys())
    print("DEBUG comparison similarity_score =", comparison.get("similarity_score"))
    print("DEBUG comparison_pdf =", comparison.get("comparison_pdf"))

    return comparison    

def compare_against_all_cases(suspect_path):
    base_dir = "cases"
    suspect_phash = get_phash(suspect_path)

    matches = []

    for case_id in os.listdir(base_dir):
        case_path = os.path.join(base_dir, case_id)
        evidence_index_path = os.path.join(case_path, "evidence_index.json")

        if not os.path.exists(evidence_index_path):
            continue

        with open(evidence_index_path, "r", encoding="utf-8") as f:
            evidence_items = json.load(f)

        for item in evidence_items:
            evidence_phash = item.get("phash")
            if not evidence_phash:
                continue

            distance = imagehash.hex_to_hash(suspect_phash) - imagehash.hex_to_hash(evidence_phash)
            similarity = max(0, round(100 - (distance * 100 / 64), 2))

            matches.append({
                "case_id": case_id,
                "evidence_id": item.get("evidence_id"),
                "file_name": item.get("file_name"),
                "distance": distance,
                "similarity": similarity,
                "pdf_report": item.get("pdf_report"),
                "json_report": item.get("json_report")
            })

    matches.sort(key=lambda x: x["distance"])

    return {
        "suspect_phash": suspect_phash,
        "matches": matches[:20]  # top 20
    }