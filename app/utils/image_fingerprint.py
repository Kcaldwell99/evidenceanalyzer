from PIL import Image
import imagehash
import os


def generate_phash(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        from pdf2image import convert_from_path
        pages = convert_from_path(file_path, first_page=1, last_page=1, dpi=150)
        if not pages:
            raise ValueError(f"Could not extract any pages from PDF: {file_path}")
        image = pages[0]
    else:
        image = Image.open(file_path)

    return str(imagehash.phash(image))