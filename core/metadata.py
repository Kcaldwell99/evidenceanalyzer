from PIL import Image, ExifTags


def get_image_metadata(path):
    metadata = {
        "format": None,
        "width": None,
        "height": None,
        "mode": None,
        "exif": {}
    }

    try:
        with Image.open(path) as img:
            metadata["format"] = img.format
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["mode"] = img.mode

            exif_data = img.getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                    metadata["exif"][tag] = str(value)

    except Exception as e:
        metadata["error"] = str(e)

    return metadata