"""
Full-file rewrite of app/utils/image_fingerprint.py.

v2: Updated EXPECTED_CURRENT to match actual file structure (blank lines,
no trailing newline). Updated normalize() to be forgiving of trailing
empty-line differences.

Adds try/except wrapping, module logger, zero-page PDF check, pdf.close()
in finally, and Optional[str] return type. Removes unused `import io`.

Run without args for dry run. Run with --write to apply.
"""

import sys
from pathlib import Path

TARGET = Path("app/utils/image_fingerprint.py")

EXPECTED_CURRENT = (
    "from PIL import Image\n"
    "import imagehash\n"
    "import os\n"
    "import io\n"
    "\n"
    "\n"
    "def generate_phash(file_path: str) -> str:\n"
    "    ext = os.path.splitext(file_path)[1].lower()\n"
    "\n"
    "    if ext == \".pdf\":\n"
    "        import pypdfium2 as pdfium\n"
    "        pdf = pdfium.PdfDocument(file_path)\n"
    "        page = pdf[0]\n"
    "        bitmap = page.render(scale=2)\n"
    "        image = bitmap.to_pil()\n"
    "    else:\n"
    "        image = Image.open(file_path)\n"
    "\n"
    "    return str(imagehash.phash(image))"
)

NEW_CONTENT_LF = (
    "from PIL import Image\n"
    "import imagehash\n"
    "import logging\n"
    "import os\n"
    "from typing import Optional\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "\n"
    "def generate_phash(file_path: str) -> Optional[str]:\n"
    "    \"\"\"Generate a perceptual hash for an image or PDF first page.\n"
    "\n"
    "    Returns None on any failure (unsupported format, corrupt file,\n"
    "    zero-page PDF, decode error). Callers must handle None.\n"
    "    \"\"\"\n"
    "    try:\n"
    "        ext = os.path.splitext(file_path)[1].lower()\n"
    "        if ext == \".pdf\":\n"
    "            import pypdfium2 as pdfium\n"
    "            pdf = pdfium.PdfDocument(file_path)\n"
    "            try:\n"
    "                if len(pdf) == 0:\n"
    "                    logger.warning(\"generate_phash: zero-page PDF at %s\", file_path)\n"
    "                    return None\n"
    "                page = pdf[0]\n"
    "                bitmap = page.render(scale=2)\n"
    "                image = bitmap.to_pil()\n"
    "            finally:\n"
    "                pdf.close()\n"
    "        else:\n"
    "            image = Image.open(file_path)\n"
    "        return str(imagehash.phash(image))\n"
    "    except Exception as e:\n"
    "        logger.exception(\"generate_phash failed for %s: %s\", file_path, e)\n"
    "        return None\n"
)


def normalize(text: str) -> str:
    """Normalize for comparison: CRLF->LF, rstrip per line, strip trailing empty lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def detect_line_ending(raw_bytes: bytes) -> str:
    """Return '\\r\\n' if file is predominantly CRLF, else '\\n'."""
    crlf = raw_bytes.count(b"\r\n")
    lf_total = raw_bytes.count(b"\n")
    lf_only = lf_total - crlf
    if crlf > lf_only:
        return "\r\n"
    return "\n"


def main() -> int:
    write = "--write" in sys.argv

    if not TARGET.exists():
        print(f"ERROR: {TARGET} does not exist", file=sys.stderr)
        return 1

    raw = TARGET.read_bytes()
    print(f"Read {len(raw)} bytes from {TARGET}")

    try:
        current_text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"ERROR: file is not valid UTF-8: {e}", file=sys.stderr)
        return 1

    # Sanity check: normalized content matches expected current.
    if normalize(current_text) != normalize(EXPECTED_CURRENT):
        print("ERROR: current file content does not match expected.", file=sys.stderr)
        print("Drift detected. Aborting to avoid clobbering unknown changes.", file=sys.stderr)
        print("--- expected (normalized) ---", file=sys.stderr)
        print(normalize(EXPECTED_CURRENT), file=sys.stderr)
        print("--- actual (normalized) ---", file=sys.stderr)
        print(normalize(current_text), file=sys.stderr)
        return 1

    line_ending = detect_line_ending(raw)
    print(f"Detected line ending: {'CRLF' if line_ending == chr(13)+chr(10) else 'LF'}")

    new_text = NEW_CONTENT_LF.replace("\n", line_ending)
    new_bytes = new_text.encode("utf-8")

    delta = len(new_bytes) - len(raw)
    print(f"Old size: {len(raw)} bytes")
    print(f"New size: {len(new_bytes)} bytes")
    print(f"Delta:    {delta:+d} bytes")

    if not write:
        print("\nDRY RUN -- no changes written. Re-run with --write to apply.")
        print("\n--- preview of new content (first 600 chars) ---")
        print(new_text[:600])
        return 0

    TARGET.write_bytes(new_bytes)
    print(f"\nWrote {len(new_bytes)} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
