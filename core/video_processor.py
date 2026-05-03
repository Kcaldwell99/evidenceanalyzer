import os
import cv2
from datetime import datetime


def extract_frames(video_path, output_dir, interval_seconds=2):
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25

    frame_interval = max(1, int(fps * interval_seconds))
    frame_count = 0
    saved_frames = []

    success, frame = cap.read()
    while success:
        if frame_count % frame_interval == 0:
            filename = f"frame_{frame_count:06d}.jpg"
            path = os.path.join(output_dir, filename)
            cv2.imwrite(path, frame)
            saved_frames.append(path)
        success, frame = cap.read()
        frame_count += 1

    cap.release()

    return {
        "frames": saved_frames,
        "total_frames": frame_count,
        "fps": fps,
        "interval_seconds": interval_seconds,
    }