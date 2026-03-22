from PIL import Image
import imagehash


def get_phash(file_path: str) -> str:
    with Image.open(file_path) as img:
        return str(imagehash.phash(img))


def phash_distance(file1: str, file2: str) -> int:
    with Image.open(file1) as img1, Image.open(file2) as img2:
        hash1 = imagehash.phash(img1)
        hash2 = imagehash.phash(img2)
        return hash1 - hash2