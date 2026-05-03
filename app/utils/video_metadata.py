import ffmpeg


def get_video_metadata(video_path):
    try:
        probe = ffmpeg.probe(video_path)
    except Exception as e:
        return {"error": str(e)}

    video_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "video"), None
    )
    audio_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "audio"), None
    )
    format_info = probe.get("format", {})

    return {
        "codec": video_stream.get("codec_name") if video_stream else None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "frame_rate": video_stream.get("r_frame_rate") if video_stream else None,
        "duration": format_info.get("duration"),
        "bitrate": format_info.get("bit_rate"),
        "format": format_info.get("format_name"),
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "audio_channels": audio_stream.get("channels") if audio_stream else None,
    }
