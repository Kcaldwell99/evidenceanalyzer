from PIL import Image
from PIL.ExifTags import TAGS

def get_image_metadata(file_path):

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

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

def extract_exif(file_path):
    try:
        with Image.open(file_path) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return {}

            exif_data = {}
            for tag, value in exif_raw.items():
                tag_name = TAGS.get(tag, tag)

                if tag_name == "GPSInfo" and isinstance(value, dict):
                    gps_data = {}
                    for gps_tag, gps_value in value.items():
                        gps_name = GPSTAGS.get(gps_tag, gps_tag)
                        gps_data[str(gps_name)] = str(gps_value)
                    exif_data["GPSInfo"] = gps_data
                else:
                    exif_data[str(tag_name)] = str(value)

            return exif_data
    except Exception as e:
        return {"error": str(e)}




    return metadata