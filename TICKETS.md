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
