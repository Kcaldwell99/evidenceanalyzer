import os
from datetime import datetime
from app.utils.hash_utils import sha256_file
from app.utils.video_metadata import get_video_metadata
from core.video_processor import extract_frames
from core.video_compare import hash_frames


def analyze_video(file_path, case_dir=None):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    frame_dir = os.path.join(case_dir or "reports", "frames", timestamp)
    frame_data = extract_frames(file_path, frame_dir)
    frame_hashes = hash_frames(frame_data["frames"])
    metadata = get_video_metadata(file_path)
    sha256 = sha256_file(file_path)

    return {
        "file_name": os.path.basename(file_path),
        "type": "video",
        "sha256": sha256,
        "metadata": metadata,
        "total_frames": frame_data["total_frames"],
        "frames_extracted": len(frame_data["frames"]),
        "frame_hashes": frame_hashes,
        "fps": frame_data["fps"],
        "interval_seconds": frame_data["interval_seconds"],
        "analysis_date": timestamp,
    }
