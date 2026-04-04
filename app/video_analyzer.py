"""
video_analyzer.py — Evidentix video forensic analysis module

Handles:
  - Video metadata extraction via ffprobe
  - Frame extraction via ffmpeg (20 frames evenly distributed)
  - Per-frame image analysis using existing analyzer
  - Combined forensic report generation
"""

import json
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# Maximum video file size in bytes (100MB)
MAX_VIDEO_SIZE = 100 * 1024 * 1024

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv"}

ALLOWED_VIDEO_MIMETYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/x-ms-wmv",
    "video/avi",
}


def check_ffmpeg():
    """Check if ffmpeg and ffprobe are available."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def extract_video_metadata(video_path: str) -> dict:
    """Extract metadata from video file using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {"error": "ffprobe failed", "stderr": result.stderr}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

        duration = float(fmt.get("duration", 0))
        size = int(fmt.get("size", 0))

        metadata = {
            "filename": fmt.get("filename", ""),
            "format": fmt.get("format_long_name", ""),
            "duration_seconds": round(duration, 2),
            "duration_display": _format_duration(duration),
            "file_size_bytes": size,
            "file_size_display": _format_size(size),
            "bit_rate": fmt.get("bit_rate", ""),
            "creation_time": fmt.get("tags", {}).get("creation_time", ""),
            "encoder": fmt.get("tags", {}).get("encoder", ""),
            "video_codec": video_stream.get("codec_name", ""),
            "video_profile": video_stream.get("profile", ""),
            "width": video_stream.get("width", ""),
            "height": video_stream.get("height", ""),
            "frame_rate": video_stream.get("r_frame_rate", ""),
            "pixel_format": video_stream.get("pix_fmt", ""),
            "audio_codec": audio_stream.get("codec_name", ""),
            "audio_sample_rate": audio_stream.get("sample_rate", ""),
            "raw_tags": fmt.get("tags", {}),
        }

        return metadata

    except Exception as e:
        return {"error": str(e)}


def extract_frames(video_path: str, output_dir: str, num_frames: int = 20) -> list:
    """Extract evenly distributed frames from video using ffmpeg."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get video duration first
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(result.stdout.strip())
    except Exception:
        duration = 60.0  # fallback

    # Calculate frame timestamps
    interval = duration / (num_frames + 1)
    timestamps = [interval * (i + 1) for i in range(num_frames)]

    extracted_frames = []

    for i, ts in enumerate(timestamps):
        frame_filename = f"frame_{i+1:03d}.jpg"
        frame_path = output_dir / frame_filename

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-ss", str(ts),
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y",
                    str(frame_path),
                ],
                capture_output=True,
                timeout=30,
            )

            if frame_path.exists() and frame_path.stat().st_size > 0:
                extracted_frames.append({
                    "frame_number": i + 1,
                    "timestamp_seconds": round(ts, 2),
                    "timestamp_display": _format_duration(ts),
                    "filename": frame_filename,
                    "path": str(frame_path),
                })
        except Exception as e:
            print(f"Failed to extract frame at {ts}s: {e}")
            continue

    return extracted_frames


def analyze_video(video_path: str, case_dir: str, file_key: Optional[str] = None) -> dict:
    """
    Full video forensic analysis.
    Returns a report dict with metadata, frames, and per-frame analysis.
    """
    from app.analyzer import analyze_file as analyze_image

    video_path = Path(video_path)
    case_dir = Path(case_dir)

    frames_dir = case_dir / "reports" / f"{video_path.stem}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "analysis_type": "video",
        "filename": video_path.name,
        "analysis_date": datetime.utcnow().isoformat(),
        "file_key": file_key,
        "metadata": {},
        "frames": [],
        "frame_analyses": [],
        "summary": {},
        "limitations": [
            "This report reflects a tool-assisted forensic analysis of the submitted video file.",
            "It does not independently establish authorship, ownership, or legal infringement.",
            "Metadata may be altered or removed during processing or transmission.",
            "Conclusions are limited to the observable characteristics of the frames analyzed.",
        ],
    }

    # Step 1: Extract metadata
    print(f"Extracting metadata from {video_path.name}...")
    report["metadata"] = extract_video_metadata(str(video_path))

    # Step 2: Extract frames
    print(f"Extracting frames from {video_path.name}...")
    frames = extract_frames(str(video_path), str(frames_dir), num_frames=20)
    report["frames"] = frames

    if not frames:
        report["summary"]["error"] = "No frames could be extracted from this video."
        return report

    # Step 3: Analyze each frame
    print(f"Analyzing {len(frames)} frames...")
    frame_analyses = []
    manipulation_flags = []

    for frame in frames:
        try:
            frame_report, json_path, pdf_path = analyze_image(
                frame["path"],
                case_dir=str(case_dir),
                file_key=None,
            )
            frame_analyses.append({
                "frame_number": frame["frame_number"],
                "timestamp": frame["timestamp_display"],
                "analysis": frame_report,
            })

            # Collect any manipulation indicators
            if frame_report.get("manipulation_detected"):
                manipulation_flags.append({
                    "frame": frame["frame_number"],
                    "timestamp": frame["timestamp_display"],
                    "indicators": frame_report.get("manipulation_indicators", []),
                })

        except Exception as e:
            frame_analyses.append({
                "frame_number": frame["frame_number"],
                "timestamp": frame["timestamp_display"],
                "error": str(e),
            })

    report["frame_analyses"] = frame_analyses

    # Step 4: Build summary
    total_frames = len(frames)
    analyzed_frames = len([f for f in frame_analyses if "error" not in f])
    flagged_frames = len(manipulation_flags)

    report["summary"] = {
        "total_frames_extracted": total_frames,
        "frames_analyzed": analyzed_frames,
        "frames_flagged": flagged_frames,
        "manipulation_flags": manipulation_flags,
        "overall_assessment": _overall_assessment(flagged_frames, analyzed_frames),
        "duration": report["metadata"].get("duration_display", ""),
        "resolution": f"{report['metadata'].get('width', '')}x{report['metadata'].get('height', '')}",
        "video_codec": report["metadata"].get("video_codec", ""),
        "creation_time": report["metadata"].get("creation_time", ""),
    }

    # Step 5: Save JSON report
    report_path = case_dir / "reports" / f"{video_path.stem}_video_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Video analysis complete. Report saved to {report_path}")
    return report


def _overall_assessment(flagged: int, total: int) -> str:
    if total == 0:
        return "Insufficient data"
    ratio = flagged / total
    if ratio == 0:
        return "No manipulation indicators detected"
    elif ratio < 0.1:
        return "Minor anomalies detected in isolated frames"
    elif ratio < 0.3:
        return "Moderate indicators of potential manipulation"
    else:
        return "Significant manipulation indicators detected across multiple frames"


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
