import os
import json
from datetime import datetime
from app.utils.hash_utils import sha256_file
from app.utils.video_metadata import get_video_metadata
from core.video_processor import extract_frames
from core.video_compare import hash_frames
from core.video_pdf import generate_video_pdf


def analyze_video(file_path, case_dir=None):
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    frame_dir = os.path.join(case_dir or "reports", "frames", timestamp)
    frame_data = extract_frames(file_path, frame_dir)
    frame_hashes = hash_frames(frame_data["frames"])
    metadata = get_video_metadata(file_path)
    sha256 = sha256_file(file_path)

    result = {
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

    output_dir = case_dir or "reports"
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(file_path))[0]
    json_path = os.path.join(output_dir, base + "_video_report_" + timestamp + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    pdf_path = os.path.join(output_dir, base + "_video_report_" + timestamp + ".pdf")
    try:
        generate_video_pdf(result, pdf_path)
    except Exception as e:
        import traceback
        print("Video PDF generation failed: " + str(e), flush=True)
        print(traceback.format_exc(), flush=True)
        pdf_path = None

    # Upload JSON and PDF to S3
    from app.storage import upload_file as s3_upload
    with open(json_path, "rb") as f:
        json_key = s3_upload(f, os.path.basename(json_path), "application/json")
    pdf_key = None
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_key = s3_upload(f, os.path.basename(pdf_path), "application/pdf")

    return result, json_key, pdf_key