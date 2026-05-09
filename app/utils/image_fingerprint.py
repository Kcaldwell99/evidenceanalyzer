from PIL import Image
import imagehash
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def generate_phash(file_path: str) -> Optional[str]:
    """Generate a perceptual hash for an image or PDF first page.

    Returns None on any failure (unsupported format, corrupt file,
    zero-page PDF, decode error). Callers must handle None.
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_path)
            try:
                if len(pdf) == 0:
                    logger.warning("generate_phash: zero-page PDF at %s", file_path)
                    return None
                page = pdf[0]
                bitmap = page.render(scale=2)
                image = bitmap.to_pil()
            finally:
                pdf.close()
        else:
            image = Image.open(file_path)
        return str(imagehash.phash(image))
    except Exception as e:
        logger.exception("generate_phash failed for %s: %s", file_path, e)
        return None
