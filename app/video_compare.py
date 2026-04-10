"""
video_compare.py — Evidentix video comparison module

Handles:
  - Frame-by-frame comparison at same positions
  - Cross-comparison of flagged sections
  - Similarity scoring and match reporting
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib

from app.video_analyzer import extract_frames, extract_video_metadata


def phash_image(image_path: str) -> Optional[str]:
    """Compute perceptual hash of an image using pillow."""
    try:
        from PIL import Image
        import imagehash
        img = Image.open(image_path)
        return str(imagehash.phash(img))
    except Exception as e:
        print(f"phash failed for {image_path}: {e}")
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute hamming distance between two hex hash strings."""
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)
        xor = int1 ^ int2
        return bin(xor).count('1')
    except Exception:
        return 64  # max distance on failure


def similarity_score(distance: int, max_bits: int = 64) -> float:
    """Convert hamming distance to 0-100 similarity score."""
    return round((1 - distance / max_bits) * 100, 1)


def compare_videos(
    video_a_path: str,
    video_b_path: str,
    case_dir: str,
    num_frames: int = 20,
) -> dict:
    """
    Full forensic comparison of two videos.
    Phase 1: Same-position frame comparison
    Phase 2: Cross-comparison on flagged sections
    """
    video_a_path = Path(video_a_path)
    video_b_path = Path(video_b_path)
    case_dir = Path(case_dir)

    # Output directories for extracted frames
    frames_dir_a = case_dir / "comparisons" / f"{video_a_path.stem}_frames"
    frames_dir_b = case_dir / "comparisons" / f"{video_b_path.stem}_frames"

    report = {
        "analysis_type": "video_comparison",
        "analysis_date": datetime.utcnow().isoformat(),
        "video_a": video_a_path.name,
        "video_b": video_b_path.name,
        "metadata_a": {},
        "metadata_b": {},
        "phase1_results": [],
        "phase2_results": [],
        "matching_pairs": [],
        "summary": {},
        "limitations": [
            "This comparison reflects tool-assisted forensic analysis.",
            "Similarity scores are based on perceptual hashing of extracted frames.",
            "Re-encoding, color grading, or resolution changes may affect scores.",
            "This report does not independently establish copyright or legal infringement.",
        ],
    }

    # Step 1: Extract metadata
    print("Extracting metadata...")
    report["metadata_a"] = extract_video_metadata(str(video_a_path))
    report["metadata_b"] = extract_video_metadata(str(video_b_path))

    # Step 2: Extract frames from both videos
    print("Extracting frames from Video A...")
    frames_a = extract_frames(str(video_a_path), str(frames_dir_a), num_frames)

    print("Extracting frames from Video B...")
    frames_b = extract_frames(str(video_b_path), str(frames_dir_b), num_frames)

    if not frames_a or not frames_b:
        report["summary"]["error"] = "Could not extract frames from one or both videos."
        return report

    # Step 3: Compute phashes for all frames
    print("Computing perceptual hashes...")
    hashes_a = []
    for f in frames_a:
        h = phash_image(f["path"])
        hashes_a.append({**f, "phash": h})

    hashes_b = []
    for f in frames_b:
        h = phash_image(f["path"])
        hashes_b.append({**f, "phash": h})

    # Step 4: Phase 1 — same-position comparison
    print("Phase 1: Same-position comparison...")
    phase1_results = []
    flagged_indices = []

    pairs = min(len(hashes_a), len(hashes_b))
    for i in range(pairs):
        ha = hashes_a[i]
        hb = hashes_b[i]

        if ha["phash"] and hb["phash"]:
            dist = hamming_distance(ha["phash"], hb["phash"])
            score = similarity_score(dist)
            flagged = score >= 85  # high similarity threshold
        else:
            dist = 64
            score = 0.0
            flagged = False

        result = {
            "position": i + 1,
            "frame_a": ha["frame_number"],
            "timestamp_a": ha["timestamp_display"],
            "frame_b": hb["frame_number"],
            "timestamp_b": hb["timestamp_display"],
            "similarity_score": score,
            "hamming_distance": dist,
            "flagged": flagged,
        }
        phase1_results.append(result)

        if flagged:
            flagged_indices.append(i)

    report["phase1_results"] = phase1_results

    # Step 5: Phase 2 — cross-comparison on flagged sections
    print(f"Phase 2: Cross-comparison on {len(flagged_indices)} flagged positions...")
    phase2_results = []
    matching_pairs = []

    # For each flagged frame in A, compare against ALL frames in B
    flagged_frames_a = [hashes_a[i] for i in flagged_indices[:5]]  # cap at 5 for performance

    for fa in flagged_frames_a:
        if not fa["phash"]:
            continue

        best_match = None
        best_score = 0

        for fb in hashes_b:
            if not fb["phash"]:
                continue
            dist = hamming_distance(fa["phash"], fb["phash"])
            score = similarity_score(dist)

            cross_result = {
                "frame_a": fa["frame_number"],
                "timestamp_a": fa["timestamp_display"],
                "frame_b": fb["frame_number"],
                "timestamp_b": fb["timestamp_display"],
                "similarity_score": score,
                "hamming_distance": dist,
            }
            phase2_results.append(cross_result)

            if score > best_score:
                best_score = score
                best_match = cross_result

        if best_match and best_match["similarity_score"] >= 85:
            matching_pairs.append(best_match)

    report["phase2_results"] = phase2_results
    report["matching_pairs"] = matching_pairs

    # Step 6: Build summary
    phase1_flagged = len(flagged_indices)
    phase1_total = len(phase1_results)
    unique_matches = len(matching_pairs)

    avg_similarity = (
        round(sum(r["similarity_score"] for r in phase1_results) / len(phase1_results), 1)
        if phase1_results else 0
    )

    max_similarity = (
        max(r["similarity_score"] for r in phase1_results)
        if phase1_results else 0
    )

    report["summary"] = {
        "frames_compared": phase1_total,
        "phase1_matches": phase1_flagged,
        "phase2_matches": unique_matches,
        "average_similarity": avg_similarity,
        "peak_similarity": max_similarity,
        "overall_assessment": _overall_assessment(phase1_flagged, phase1_total, max_similarity),
        "duration_a": report["metadata_a"].get("duration_display", ""),
        "duration_b": report["metadata_b"].get("duration_display", ""),
        "resolution_a": f"{report['metadata_a'].get('width','')}x{report['metadata_a'].get('height','')}",
        "resolution_b": f"{report['metadata_b'].get('width','')}x{report['metadata_b'].get('height','')}",
    }

    # Step 7: Save report
    report_path = case_dir / "comparisons" / f"video_comparison_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Video comparison complete. Report: {report_path}")
    return report


def _overall_assessment(flagged: int, total: int, peak: float) -> str:
    if total == 0:
        return "Insufficient data for comparison."
    ratio = flagged / total
    if peak >= 95:
        return "Near-identical content detected — videos are likely the same source."
    elif peak >= 85 and ratio >= 0.5:
        return "High similarity detected — videos likely share common source material."
    elif peak >= 75 or ratio >= 0.25:
        return "Moderate similarity detected — possible relationship between videos."
    elif peak >= 60:
        return "Low similarity — minor visual overlap detected."
    else:
        return "No significant similarity detected between videos."
