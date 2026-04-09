from PIL import Image
import imagehash
import os
import io


def generate_phash(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(file_path)
        page = pdf[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil()
    else:
        image = Image.open(file_path)

    return str(imagehash.phash(image))