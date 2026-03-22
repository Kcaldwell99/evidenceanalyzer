from PIL import Image
import imagehash


def generate_phash(file_path: str) -> str:
    image = Image.open(file_path)
    return str(imagehash.phash(image))