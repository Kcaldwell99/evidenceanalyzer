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
