"""
Close ticket #4 in TICKETS.md.

Mechanical changes:
  1. Remove the entire `### #4 ...` block from the Open section.
  2. Append a new `### #4 ...` close entry to the end of the file
     (Closed section).

TICKETS.md uses em-dashes (real U+2014, encoded as 3 bytes in UTF-8),
so this is byte-level Python (not PowerShell str_replace).

Sanity checks:
  - Pre: exactly one "### #4 — image_fingerprint.py" in Open section.
  - Pre: exactly one "## Closed" header.
  - Post: exactly one "### #4 — image_fingerprint.py" total (in Closed).
  - Post: exactly one "## Closed" header.
  - Post: same count of every other `### #N —` heading as before.

Run without args for dry run. Run with --write to apply.
"""

import sys
from pathlib import Path

TARGET = Path("TICKETS.md")

# Anchors
TICKET_4_START = "### #4 \u2014 image_fingerprint.py"  # \u2014 = em dash
CLOSED_HEADER = "## Closed"

# New close entry to append. Em-dashes use \u2014.
CLOSE_ENTRY = (
    "\n"
    "### #4 \u2014 image_fingerprint.py: missing PIL import + unconfirmed PDF error\n"
    "\n"
    "**Closed in commit 3dba819 (May 8, 2026).** Verified live in prod with both image (JPG) and PDF uploads \u2014 both succeed with no errors logged.\n"
    "\n"
    "**Issue 1 (missing PIL import):** Retracted earlier same day \u2014 was a misread (line 1 of the file was clipped in the original `Get-Content` screenshot). The import was already present.\n"
    "\n"
    "**Issues 2 and 3 (PIL error on PDF + no graceful degradation):** Closed by a single rewrite of `app/utils/image_fingerprint.py` rather than per-call-site try/except. Changes:\n"
    "- Wraps the entire function body in `try/except Exception`; returns `Optional[str]` (None on any failure); logs via `logger.exception`.\n"
    "- Adds an explicit zero-page PDF check with a `logger.warning`.\n"
    "- Wraps the PDF branch in `try/finally` for `pdf.close()` (resource leak fix).\n"
    "- Removes unused `import io`.\n"
    "\n"
    "Fixed at the function rather than at call sites: one edit instead of six, future call sites get the safety automatically, function now has a clear `Optional[str]` contract.\n"
)


def detect_line_ending(raw_bytes: bytes) -> str:
    crlf = raw_bytes.count(b"\r\n")
    lf_total = raw_bytes.count(b"\n")
    lf_only = lf_total - crlf
    return "\r\n" if crlf > lf_only else "\n"


def main() -> int:
    # Force UTF-8 stdout/stderr so non-ASCII (em-dashes etc.) don't choke PowerShell's cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    write = "--write" in sys.argv

    if not TARGET.exists():
        print(f"ERROR: {TARGET} does not exist", file=sys.stderr)
        return 1

    raw = TARGET.read_bytes()
    print(f"Read {len(raw)} bytes from {TARGET}")

    text = raw.decode("utf-8")
    line_ending = detect_line_ending(raw)
    print(f"Detected line ending: {'CRLF' if line_ending == chr(13)+chr(10) else 'LF'}")

    # Normalize internally to LF for slicing; convert back at end.
    norm = text.replace("\r\n", "\n")

    # ---- Pre-checks ----
    n_t4 = norm.count(TICKET_4_START)
    n_closed = norm.count(CLOSED_HEADER)
    if n_t4 != 1:
        print(f"ERROR: expected exactly 1 occurrence of {TICKET_4_START!r}, found {n_t4}", file=sys.stderr)
        return 1
    if n_closed != 1:
        print(f"ERROR: expected exactly 1 occurrence of {CLOSED_HEADER!r}, found {n_closed}", file=sys.stderr)
        return 1
    print(f"Pre-check: '### #4 ...' count = {n_t4}, '## Closed' count = {n_closed}")

    # Save heading counts for post-check
    pre_h_counts = {f"#{i}": norm.count(f"### #{i} \u2014") for i in (1, 2, 3, 4)}
    print(f"Pre-check heading counts: {pre_h_counts}")

    # ---- Operation 1: cut #4 block from Open ----
    i_t4 = norm.find(TICKET_4_START)
    i_closed = norm.find(CLOSED_HEADER)
    if i_closed <= i_t4:
        print("ERROR: '## Closed' appears before '### #4'. Unexpected file structure.", file=sys.stderr)
        return 1

    # Cut from start of #4 (inclusive) to start of `## Closed` (exclusive).
    # This removes: "### #4 [...content...]\n\n---\n\n"
    # Leaves: "...end of #2 content...\n\n---\n\n## Closed..."
    new_norm = norm[:i_t4] + norm[i_closed:]

    # ---- Operation 2: append close entry at end of file ----
    new_norm = new_norm.rstrip() + "\n" + CLOSE_ENTRY

    # ---- Post-checks ----
    post_n_t4 = new_norm.count(TICKET_4_START)
    post_n_closed = new_norm.count(CLOSED_HEADER)
    if post_n_t4 != 1:
        print(f"ERROR (post): expected 1 occurrence of {TICKET_4_START!r}, got {post_n_t4}", file=sys.stderr)
        return 1
    if post_n_closed != 1:
        print(f"ERROR (post): expected 1 occurrence of {CLOSED_HEADER!r}, got {post_n_closed}", file=sys.stderr)
        return 1
    post_h_counts = {f"#{i}": new_norm.count(f"### #{i} \u2014") for i in (1, 2, 3, 4)}
    if post_h_counts != pre_h_counts:
        print(f"ERROR (post): heading counts changed.", file=sys.stderr)
        print(f"  pre:  {pre_h_counts}", file=sys.stderr)
        print(f"  post: {post_h_counts}", file=sys.stderr)
        return 1
    # Confirm #4 now appears AFTER ## Closed (i.e., it's in the Closed section)
    if new_norm.find(TICKET_4_START) <= new_norm.find(CLOSED_HEADER):
        print("ERROR (post): '### #4' is not in the Closed section.", file=sys.stderr)
        return 1
    print(f"Post-check: '### #4' count = {post_n_t4}, '## Closed' count = {post_n_closed}, headings unchanged")
    print("Post-check: '### #4' is now in the Closed section. OK")

    # ---- Convert back to original line ending ----
    new_text = new_norm.replace("\n", line_ending)
    new_bytes = new_text.encode("utf-8")

    delta = len(new_bytes) - len(raw)
    print(f"Old size: {len(raw)} bytes")
    print(f"New size: {len(new_bytes)} bytes")
    print(f"Delta:    {delta:+d} bytes")

    if not write:
        print("\nDRY RUN -- no changes written. Re-run with --write to apply.")
        return 0

    TARGET.write_bytes(new_bytes)
    print(f"\nWrote {len(new_bytes)} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
