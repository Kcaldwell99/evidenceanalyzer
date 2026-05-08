# Tickets

Tracking known issues and planned work for Evidentix.

---

## Open

### #2 — No tier limit enforcement on video upload route

**Severity:** Medium. Allows monitoring-tier users to bypass file count limits by uploading videos instead of images.

**Location:** `app/main.py`, video upload route around line 2102 (`new_item = EvidenceItem(...)` block).

**Description:**
The image upload route (`analyze_file_route`, line 502) enforces monitoring tier file count limits via `get_active_monitoring_sub` + `TIER_LIMITS` check (added in commit e390266). The video upload route has no equivalent check. A monitoring-tier user at their file limit can continue uploading videos indefinitely.

**Reproduction:**
1. Set up a user with an active `monitoring_small` subscription (tier_limit=25).
2. Upload 25 image files via the image route. The 26th is rejected with HTTP 403.
3. Switch to the video upload route. Upload videos. No limit enforcement — all succeed.

**Suggested fix:**
Mirror the pattern from `analyze_file_route` (commit e390266):
- Fetch `sub = get_active_monitoring_sub(current_user.id, db)` early in the route, after auth/ownership checks but before any S3 upload, analysis, or DB writes.
- If `sub` exists, check `current_count >= tier_limit` against EvidenceItem count for the case.
- Raise 403 before any side effects.

**Open questions before fixing:**
- Confirm whether video uploads count toward the same `EvidenceItem` table as images (likely yes given `EvidenceItem` constructor at line 2102 looks identical to line 544's), or if they're tracked separately. The current_count query depends on this.
- Confirm whether tier limits should apply equally to videos and images, or if video uploads should have a separate tier_limit (e.g., videos count more because of storage).

**Notes:**
- Surfaced during the orphan EvidenceItem fix (commit e390266, May 8, 2026).
- Same orphan-on-overage problem will apply if a check is added without putting it at the start of the route.

---

### #4 — image_fingerprint.py: missing PIL import + unconfirmed PDF error

**CORRECTION (May 8, 2026 — later same day):** Issue 1 below was wrong. `from PIL import Image` IS present at the top of `image_fingerprint.py` (line 1). The original investigation misread the file because an early `Get-Content` screenshot clipped the first line, and the misread was carried forward through the rest of the analysis. An attempted "fix" added a duplicate import; it was caught by `git diff` (showed two `from PIL import Image` lines), reverted via `git restore`, never committed. **Issues 2 and 3 still stand.** Issue 1 below is preserved as written for posterity / lessons learned.

**Lessons learned:**
- Don't trust screenshot output of `Get-Content` for files where line 1 might be clipped. Either scroll up before pasting, or check file content with `git show` / `Select-String -Pattern "."` to be sure.
- The `git diff` review step caught this before commit. The pattern works.

**Severity:** Medium-High. `generate_phash()` is on the critical path for every image upload, every comparison, and batch scans. No try/except wrapping at any call site, so a failure 500s the whole request.

**Location:** `app/utils/image_fingerprint.py` (15 lines, the entire file).

**Investigation summary (May 8, 2026):**

Two issues identified.

**Issue 1 — Missing `PIL.Image` import (high confidence):** [WRONG — see correction at top of ticket. The import IS there.]

The file's else branch (line 16) does `image = Image.open(file_path)`, but `Image` is never imported. Top-of-file imports are only `imagehash`, `os`, `io`. This branch handles all non-PDF uploads (jpg, png, etc.) and will raise `NameError: name 'Image' is not defined` at runtime.

Per `git log`, the else branch with this missing import has been present since commit `d703b4d` ("handle PDF input in generate_phash via pdf2image"). Two subsequent commits, no fix. The fact that this hasn't surfaced as a major user issue suggests either:
- Nearly all production uploads through this path have been PDFs (took the if-branch).
- The NameError surfaces as a generic HTTP 500 and hasn't been investigated.
- Some upstream caller catches and swallows (no evidence of this).

**Issue 2 — "PIL error on PDF upload" (the rollover's flagged bug):**

The PDF branch uses `page.render(scale=2).to_pil()`, which matches the current pypdfium2 v4 API per the official documentation. So the bug is most likely runtime-environmental, not an API mismatch. Likely candidates:
- Pillow not actually installed in the prod runtime (despite being in requirements.txt — possible if Render's build skipped it).
- Bitmap format mismatch between installed pypdfium2 and Pillow versions.
- Specific malformed PDFs failing pypdfium2's rendering pipeline.

Cannot confirm without prod error logs.

**Issue 3 — No graceful degradation:**

Every call site invokes `generate_phash(...)` without try/except wrapping:
- `app/analyzer.py:44` — every upload through `analyze_file_route`.
- `core/batch_scan.py:17` — batch scan.
- `core/compare_files.py:414, 415, 575` — comparison features.

A phash failure 500s the entire upload/comparison rather than degrading to phash=None and continuing. Even if Issues 1 and 2 are fixed, future failures (corrupt files, unsupported formats) would still 500.

**Suggested fix sequence:**

1. **One-line fix for Issue 1:** ~~add `from PIL import Image` to top of `app/utils/image_fingerprint.py`. Probably ship this immediately — high confidence, trivial change.~~ **N/A — already imported.**

2. **Pull Render error logs** for occurrences of "phash", "Image", or 500s on `/analyze`. The actual error message will scope Issue 2 precisely. Until logs are reviewed, Issue 2 is speculation.

3. **Wrap call sites in try/except** so phash failures degrade gracefully:
   ```python
   try:
       phash = generate_phash(file_path)
   except Exception:
       phash = None  # or log and continue
   ```
   Apply to all 4 call sites. Small refactor, low risk.

4. **Add tests** for both branches with sample files (one PDF, one PNG). Prevents future regressions.

**Notes:**
- Investigation done in "scope only" mode — no code changes yet, no commits to `image_fingerprint.py`.
- `pypdfium2` is not installed in Ken's local venv, so local reproduction would require a `pip install pypdfium2 pillow` first.

---

## Closed

### #1 — Orphan EvidenceItem on tier limit overage

**Closed in commit e390266 (May 8, 2026).**

The image upload route (`analyze_file_route`) committed EvidenceItem, audit log entries, fingerprint index entries, and S3 objects before checking the tier limit. Over-limit users got a 403 but the side effects were already permanent. Fixed by moving the tier check to the start of the route, before any work happens. Comparison changed from `>` to `>=` since the check now runs before adding rather than after.

### #3 — Custody log entries with null evidence_id

**Closed May 8, 2026. No action taken — historical records, chain integrity confirmed via indirect evidence.**

**Investigation findings:**
- 168 total rows in `custody_log` with null `evidence_id`.
- 122 rows have legitimately null `evidence_id` (action types where no single evidence item applies: `comparison_performed`, `global_comparison_completed`, `video_comparison_performed`, `case_deleted`, `custody_log_cleared`).
- 41 rows are "orphans" — actions that should have populated `evidence_id` (`file_uploaded`, `analysis_completed`, `file_viewed`, `evidence_deleted`, `video_analyzed`).
- Of those 41: 6 are pre-chain (chain_hash null), 35 are in-chain (chain_hash populated).

**Why no action:**
- The `custody_log` is a hash-chained audit trail. Its purpose is forensic integrity. Deleting historical rows erases history; modifying historical rows (e.g. backfilling evidence_id) would break chain verification when `verify_chain` recomputes hashes.
- Per-case chains (`verify_chain` at `app/utils/audit_log.py:162` filters by `case_id`), so each case's integrity is independent.
- The orphan rows were inserted with null `evidence_id` and their `chain_hash` was computed at that moment over their actual content. When `verify_chain` recomputes today, it reads the row back, gets null, computes the same hash, matches. Chains are intact.
- If chains were broken, custody record PDF generation would fail in prod. No reports of such failures, so chains are confirmed intact via indirect evidence.
- Future code paths that use `log_audit_event` correctly populate `evidence_id` where applicable, so no new orphans are being created.

**If formal verification is wanted later:** call `verify_chain(case_id)` for each distinct case_id in the custody_log and confirm all return `(True, None, None)`.
