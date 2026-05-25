import os

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Mirror web_detection.py: extensions PIL can reliably read.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def _is_image(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in IMAGE_EXTENSIONS


def get_image_metadata(file_path):
    if not _is_image(file_path):
        return {}
    metadata = {}
    try:
        img = Image.open(file_path)
        exif = img._getexif()
        if exif:
            for tag, value in exif.items():
                decoded = TAGS.get(tag, tag)
                metadata[str(decoded)] = str(value)
    except Exception as e:
        metadata["error"] = str(e)
    return metadata  # fixed


def extract_exif(file_path):
    if not _is_image(file_path):
        return {}
    try:
        with Image.open(file_path) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return {}

            exif_data = {}
            for tag, value in exif_raw.items():
                tag_name = TAGS.get(tag, tag)

                if tag_name == "GPSInfo" and isinstance(value, dict):
                    for gps_tag, gps_value in value.items():
                        gps_name = GPSTAGS.get(gps_tag, gps_tag)
                        exif_data[f"GPS_{gps_name}"] = str(gps_value)  # fixed
                else:
                    exif_data[str(tag_name)] = str(value)

            return exif_data
    except Exception as e:
        return {"error": str(e)}


def _dms_to_decimal(dms, ref):
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def extract_gps(file_path):
    """Return (latitude, longitude) as decimal degrees if EXIF contains GPS, else None."""
    if not _is_image(file_path):
        return None
    try:
        with Image.open(file_path) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return None
            gps_info = None
            for tag, value in exif_raw.items():
                if TAGS.get(tag, tag) == "GPSInfo" and isinstance(value, dict):
                    gps_info = {GPSTAGS.get(k, k): v for k, v in value.items()}
                    break
            if not gps_info:
                return None
            lat_dms = gps_info.get("GPSLatitude")
            lat_ref = gps_info.get("GPSLatitudeRef")
            lon_dms = gps_info.get("GPSLongitude")
            lon_ref = gps_info.get("GPSLongitudeRef")
            if not (lat_dms and lat_ref and lon_dms and lon_ref):
                return None
            lat = _dms_to_decimal(lat_dms, lat_ref)
            lon = _dms_to_decimal(lon_dms, lon_ref)
            if lat is None or lon is None:
                return None
            return (lat, lon)
    except Exception:
        return None