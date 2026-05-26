# EVIDENTIX ROLLOVER — 2026-05-26

**Session date:** Monday, May 25, 2026 evening → Tuesday, May 26, 2026
**Commit volume:** 15 production changes (13 git commits + 2 Stripe operations + 1 Stripe webhook config change)
**Major artifacts:** AI-sanctions landing page (8 sections drafted, reviewed, locked, captured to git)
**Critical bugs resolved:** Stripe webhook 100% error rate; production login regression
**Status going into next session:** All production endpoints functional. Webhook fully working. SKU catalog cleaned. Landing page copy complete, build pending.

---

## Session context

Kenneth Caldwell — founding attorney Caldwell Law Firm, sole founder/developer of Evidentix™ (evidenceanalyzer.com, Evidence Analyzer, LLC TX). Solo developer, Python/FastAPI on Windows PowerShell + VS Code. Repo: `C:\Users\kcald\c2pa-evidence-mvp\`. GitHub: `github.com/Kcaldwell99/evidenceanalyzer`. Push pattern: `git push origin dev:main` (Render deploys from main). S3 bucket: `evidentix-files-ken01` (us-west-2).

Standing rules confirmed this session:
- Always `git add -f` for new files
- Use `[System.IO.File]::WriteAllText()` UTF-8 no BOM
- Never paste Python into PowerShell — write to .py file and run
- Don't paste the PowerShell prompt prefix when copying commands
- `tools/*.py` and `tools/*.ps1` are gitignored — kept local for development

---

## What we shipped (15 production changes in chronological order)

### Commit 1: Retire Firm License SKU
**Hash:** `ba92694..8c334c8`
**Files:** `app/main.py` (3-line comment-out across STRIPE_PRICES, PRICING, SUBSCRIPTION_PRODUCTS)
**Why:** Despite TOS Section 13 listing it as retired, `/checkout/firm` was an active $7,500/yr Stripe checkout. Zero active subscriptions. Killed via standard SKU kill pattern.
**Stripe product:** `prod_UG185bp0VvVXR6`
**Stripe price:** `price_1THV6cHVHQNKUlwkViPyHk4f`

### Operation 2: Stripe archive — Firm License
Archived in Stripe dashboard after code kill.

### Commit 3: .gitignore hygiene
**Hash:** `8c334c8..3a80fe7`
**Why:** Add patterns for backup files (.bak.*), .DS_Store, etc. Round 1 of hygiene work.

### Commit 4: Banner cleanup Op B
**Hash:** `3a80fe7..61a67b2`
**Files:** `app/templates/login.html`, `app/templates/register.html`
**Why:** Remove duplicate / mojibake-affected banners. Took 4 attempts (v1-v4) due to PowerShell here-string line-ending interactions.
**Lesson banked:** PowerShell here-strings inherit script-file line endings. When a script is written on LF systems but the target file is CRLF, multi-line patterns won't match. Solution: build patterns with explicit `$lines -join "`r`n"` or detect file's native line ending first.

### Commit 5: Metadata utils PDF guard
**Hash:** `61a67b2..1da9edd`
**Files:** `app/utils/metadata_utils.py`
**Why:** PDFs were being passed to `Image.open()` (PIL) which can't open PDFs, throwing exception that was caught and turned into a misleading error string. Added `_is_image()` helper and guard at the top of `get_image_metadata`, `extract_exif`, `extract_gps`.

### Commit 6: Brand-patch compare.html
**Hash:** `1da9edd..53e05b2`
**Files:** `app/templates/compare.html`
**Why:** Match the dark theme established for login.html/register.html. Form input page, not result page.

### Commit 7: Retire Professional Plan SKU
**Hash:** `53e05b2..b94ca4a`
**Files:** `app/main.py` (3-line comment-out)
**Why:** Investigation revealed `professional` only appeared in 3 places in main.py (the three dicts), nowhere in code logic. No SERVICE_MAP entry, no gating, no feature differentiation — phantom product. Mismatched pricing in Stripe description vs. pricing.html cap. Zero subscribers, $0 MRR. Killed.
**Stripe product:** `prod_UG14zntcikcSFC`
**Stripe price:** `price_1THV2DHVHQNKUlwkZ5lyCBsE`

### Operation 8: Stripe archive — Professional Plan
Archived in Stripe dashboard after code kill.

### Commit 9: Add `tools/*.py` to .gitignore
**Hash:** `b94ca4a..ebf26f4`
**Why:** The audit script (`tools/audit_payments_subscriptions_20260525.py`) needed to be local-only. Added rule.

### Commit 10: Fix webhook handler — data_object.to_dict() **(CRITICAL BUG FIX)**
**Hash:** `ebf26f4..b107044`
**Files:** `app/main.py` (one-line change at line 1182)

**Bug:** Stripe webhook was returning HTTP 500 on every delivery (100% error rate). Render logs showed:

```
File "/opt/render/project/src/app/main.py", line 1190, in stripe_webhook
  customer_details = data_object.get("customer_details") or {}
File ".../stripe/_stripe_object.py", line 173, in __getattr__
  raise AttributeError(*err.args) from err
```

Root cause: `event["data"]["object"]` returns a Stripe SDK Session object, not a dict. `.get()` on Stripe object raises AttributeError. The bug was introduced when commit `c2dab24` refactored from `json.loads(payload)` to `stripe.Webhook.construct_event(...)`.

**Fix:**
```python
# Before (line 1182):
data_object = event["data"]["object"]
# After:
data_object = event["data"]["object"].to_dict()
```

`.to_dict()` recursively converts nested Stripe objects to plain dicts. All downstream `.get()` calls work as written.

**Verified live:** Resent failed event from Stripe dashboard. Status went 500 → 200. New Payment row written with product, event_id, amount populated correctly.

### Commit 11: Fix webhook subscription handler — stripe_sub.to_dict()
**Hash:** `b107044..c3a5cda`
**Files:** `app/main.py` (one-line change at line 1221)
**Why:** Same bug pattern at the `stripe.Subscription.retrieve()` call. Pre-emptive fix. Will only matter once a real subscription event fires.

### Operation 12: Stripe webhook config — add 4 subscription events
Added in Stripe dashboard. Previously only `checkout.session.completed`. Now also:
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

"Listening to: 5 events" confirmed in destination overview.

### Commit 13: AI-sanctions landing page draft + build items
**Hash:** `c3a5cda..58861e6`
**Files:** `docs/Evidentix_AI_Sanctions_Landing_Page_Draft.md`, `docs/Evidentix_AI_Sanctions_Landing_Page_Build_Items.md`
**Why:** Captured all 8 sections of the AI-sanctions landing page as a durable strategy artifact. Plus a companion implementation document. See "Landing page status" section below.

**Recovery note:** First Move-Item silently renamed the Draft file to `docs` (no extension) when the docs/ folder didn't exist yet. Recovered via Rename-Item to `_recovered_docs_file.md`, then created actual docs/ directory.

### Commit 14: Brand-patch compare_result.html
**Hash:** `58861e6..364977f`
**Files:** `app/templates/compare_result.html`
**Why:** Match the dark theme. 153-line template with 15 Jinja variables and 12 control blocks. All preserved verbatim. 260 insertions / 149 deletions.

### Commit 15: Fix upload.html — remove retired SKUs from pricing slug list **(CRITICAL REGRESSION FIX)**
**Hash:** `364977f..eda41ce`
**Files:** `app/templates/upload.html` (line ~482)

**Bug:** After commit 14 deployed, login broke with HTTP 500 → dashboard rendering crash:
```
File "/opt/render/project/src/app/templates/upload.html", line 488, in top-level template code
  <h3>{{ p.name }}</h3>
jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'professional'
```

Root cause: `upload.html` had a hardcoded slug list at line 482:
```jinja
{% for slug in ["monitoring_small", "monitoring_standard", "monitoring_large", "professional", "firm"] %}
{% set p = pricing[slug] %}
```

The SKU kills in commits 1 and 7 removed `professional` and `firm` from the `pricing` dict in main.py. The template still iterated over them. Removed retired slugs from the list:

```jinja
{% for slug in ["monitoring_small", "monitoring_standard", "monitoring_large"] %}
```

**Verified live:** Login works again. Dashboard renders cleanly.

---

## AI-sanctions landing page — status

**Strategic frame (locked):**
- Page sells only Integrity Certificate (not Custody Record, not Monitoring)
- Single page (Model C) for all 4 buyer segments — segment variants only if data justifies
- CTA mechanic: EVIDENTIX100 promo at /pricing checkout (path B — easier to ship; trial migration deferred)
- Kenneth stays anonymous as "attorney-built"
- Hero copy locked from May 6 session

**All 8 sections finalized:**

| # | Section | Status |
|---|---|---|
| 1 | Hero | ✅ Final (carried from May 6) |
| 2 | Sanctions wall | ✅ Final (kept as drafted: Mendones/Whiting/Liar's Dividend + footnote 3 + $5K era line + emotional transition) |
| 3 | Integrity Certificate (product moment) | ✅ Final (rephrased to "PDF report" not "four-page"; AI provenance flags narrowed to C2PA-only) |
| 4 | Two scenarios (side-by-side cards) | ✅ Final (PI carrier $4M staged-accident + copyright § 512(f) misrepresentation; Certificate's-role callouts cut) |
| 5 | How it works (3 numbered steps) | ✅ Final ("minutes, not hours"; signing language rephrased — Certificate is hash+timestamp, not signed) |
| 6 | Why Evidentix (3 columns) | ✅ Final (Do Nothing / Forensic Expert $5K-$50K / Free Tools; free-tools concession cut) |
| 7 | FAQ (6 strategic questions) | ✅ Final (Admissibility / Authority / Custody-testimony / Discovery / Cost-over-time / Privacy) |
| 8 | Final CTA | ✅ Final (button "Try one Certificate free"; "Use code EVIDENTIX100 at checkout"; verified no-card-required at $0) |

**Saved to git:**
- `docs/Evidentix_AI_Sanctions_Landing_Page_Draft.md` (19,504 bytes) — full consolidated copy
- `docs/Evidentix_AI_Sanctions_Landing_Page_Build_Items.md` (12,924 bytes) — implementation tasks

---

## Open items going into the next session (priority order)

### Tier 1 — Critical (blocks landing page launch)

1. **Generate a real Integrity Certificate sample.** Current `/sample` route returns a Custody Record format, not an Integrity Certificate format. Section 3 thumbnail and Section 8 sample CTA both link to this. **Discovered today:** the sample PDF visible at `https://evidenceanalyzer.com/sample` is titled "EVIDENTIX™ INTEGRITY & CHAIN OF CUSTODY REPORT" with Exhibit A (hash table) and Exhibit B (custody log) — that's a Custody Record, not an Integrity Certificate. Need to:
   - Generate single-file Integrity Certificate via production app
   - Export PDF, verify format
   - Upload to S3 as canonical sample with public-read ACL
   - Update `/sample` redirect target

2. **SERVICE_MAP rebuild for `integrity_certificate` and `custody_record`.** This is the elephant we've been deferring all month. With the webhook now correctly capturing data, the next purchase of any non-`single` SKU would write a clean Payment row and then **crash at intake** because `SERVICE_MAP[service]` only has entries for `single`, `comparison`, `investigation`. Two paths:
   - Path A: Build SERVICE_MAP entries for the surviving SKUs (`integrity_certificate`, `custody_record`, `video_single`, `bundle`, `video_image_bundle`, `video_bundle`)
   - Path B: Refactor intake handler to use STRIPE_PRICES as source of truth
   **This blocks any landing page launch that sells anything other than the legacy `single` product.**

3. **Confirm Mendones/Whiting/Delfino citation accuracy.** Three footnotes carry legal-credibility weight on the landing page. Pull complete official cites before launch.

### Tier 2 — Build the page

4. **Build HTML template** `app/templates/ai_sanctions.html` extending `base.html`. Dark theme matching login/register/compare/compare_result. Eight `<section>` blocks. Estimated 6-10 hours.
5. **Wire route** `/ai-sanctions` (default suggested, reconsider at build time).
6. **SEO + meta tags + social card image** (1200×630) for Google Ads landing approval.
7. **Analytics + conversion tracking** — gtag with existing conversion ID `AW-18099032758`.
8. **End-to-end conversion test** — visit landing → click CTA → /pricing → enter EVIDENTIX100 → reach intake → confirm Payment row writes.

### Tier 3 — Critical operational gaps

9. **SKU kill protocol audit.** **Lesson banked tonight:** removing entries from `STRIPE_PRICES`/`PRICING`/`SUBSCRIPTION_PRODUCTS` is not sufficient if templates iterate over those dicts via hardcoded slug lists. Required addition to every future SKU kill: search all templates for hardcoded references to the slug. If found, update the template's slug list. Example check command:
   ```powershell
   Get-ChildItem app/templates -Filter "*.html" | Select-String -Pattern '"<slug>"' -SimpleMatch
   ```
   We caught this tonight via real-user login crash. Don't want to catch it that way again.

10. **Webhook subscription path is untested in production.** Lines 1205-1264 of the webhook handler (subscription event handling) have never executed because (a) Stripe wasn't subscribed to those event types until tonight, and (b) all test purchases have been with EVIDENTIX100 ($0 promo) which doesn't fire any webhook events. Once a real subscription fires, we'll learn whether line 1221 (the `stripe.Subscription.retrieve().to_dict()` fix) was correct. May need additional fixes.

### Tier 4 — 14-day trial build (future-state CTA)

11. **14-day trial implementation.** Per May 5 scope, ~14-16 hours across ~4 focused sessions:
   - Phase 1 (~3 hr): DB migrations + signup flow changes
   - Phase 2 (~5 hr): Feature gating middleware
   - Phase 3 (~4 hr): Trial-aware UI (banner, counters, expired-state overlays)
   - Phase 4 (~3 hr): Email cadence (5 emails via Render cron)
   - Phase 5 (post-launch): Admin & analytics
   
   When complete, swap landing page CTA from "Try one Certificate free" + EVIDENTIX100 to "Free 14-day trial — no card required" + `/trial` route. Keep EVIDENTIX100 alive for cold outreach (already in templates and one-pagers).

### Tier 5 — Active litigation matters (per May 23 rollover, still in flight)

- *Becker v. City of Smithville* — Rule 26(a)(1) disclosures + First Amended Complaint + motion for leave drafted, awaiting filing
- *Petersen v. Elux Homes* — voluntary dismissal strategy + Amended Petition + MTD opposition pending
- *Temporary Love LLC matters* — extensive filings drafted across 2 receivership proceedings, awaiting filing
- *Anderson Law LLC v. Clifton, Temporary Love* — Answer drafted
- *Foster v. Lakeview Village* — deposition prep packet drafted
- *Hendrix v. LCCA* — Rule 37 deficiency letter, depo memo, Rule 30(b)(6) notice (48 sub-topics), Rule 45 subpoena for Amber Askren (missing caption/date/location)
- *Love v. Walmart* — interrogatory answers + supplemental RFP responses drafted
- *M&G 114 v. HJM Architects* — Motion for Leave + Reply brief drafted. **Critical:** damages interrogatory answer says "$1,283.45" — likely typo requiring supplemental correction
- *Hashmami v. Anwar* (CCB) — Party Statement (v7), Witness Statement (v5), Evidence List (v8) ready for filing

### Tier 6 — Operational cleanup (deferred from May 23, still open)

12. **Subpoena runbook + legal@ monitoring** (compliance)
13. **Cookie consent UI** — DOM check showed no UI on /login despite policy promising it
14. **Custody log null evidence_id cleanup** (legacy data)
15. **Other compare_*_result.html template orphans:** `compare_case_result.html`, `compare_global_result.html`, `video_compare_result.html` — all need brand patches matching compare_result.html
16. **`compare_direct_result.html` — DEAD CODE** — confirmed tonight that no .py file and no template references it. Safe to delete in a future cleanup session.
17. **Em-dash mojibake** in webhook idempotency comment (`â€"` at line 1184 area)
18. **Stripe webhook destination description typo** — "Check Out Session Complete" → "Checkout Session Complete"
19. **.gitattributes + LF normalization** (~29 files need normalization)
20. **Legacy entity reference cleanup** — some templates still reference CLF The Woodlands LLC instead of Evidence Analyzer, LLC (TX)
21. **c2pa_analysis.py vs web_detection.py "what is an image" inconsistency**
22. **Two old recovery files in repo root** (`recovered_checkout_code.txt`, `recovered_webhook_code.txt` from 4/24) — investigate and clean up

---

## Production state at end of session

- ✅ Stripe webhook fully working (3 successful deliveries today after fix)
- ✅ Login + dashboard render correctly
- ✅ /compare and /compare_result render in dark theme matching login/register
- ✅ Two retired SKUs (Firm License, Professional Plan) archived in Stripe and removed from code+templates
- ✅ Privacy Policy + TOS live since May 23
- ✅ Cookie banner + EVIDENTIX100 promo + admin mailbox + Google Ads conversion tracking all live since prior sessions
- ✅ Database has clean recent Payment rows from today's webhook tests (ids 8, 9 with proper product/event_id/amount)
- ❌ No real subscription transactions ever processed — subscription handler still untested in production
- ❌ SERVICE_MAP still gates intake form behind 3 legacy slugs only — blocks any non-`single` SKU from completing intake
- ❌ Sample Certificate URL serves a Custody Record format, not an Integrity Certificate

---

## Decisions banked tonight (don't re-relitigate)

- **Landing page CTA mechanic = EVIDENTIX100 (path B), not 14-day trial.** Faster to ship. Trial migration is post-launch work.
- **Page = single page for all 4 segments (Model C).** Segment-specific landing pages only if data justifies.
- **Kenneth stays anonymous on the page.** "Attorney-built," not Kenneth-named.
- **Section 6 = competitive positioning** (3 alternatives), not design rationale.
- **Section 7 FAQ = 6 strategic objections, not generic documentation.**
- **The Section 3 sample needs to be a real Integrity Certificate.** Custody Record won't substitute.

---

## Lessons banked for next session

1. **SKU kills must include template audit.** See open item #9 above.
2. **PowerShell here-strings inherit script-file line endings.** When patching files in this repo, build patterns with `$lines -join "`r`n"` or detect file's native line ending.
3. **`Select-String -SimpleMatch` doesn't work with regex escape characters.** Patterns like `\[`, `\(`, `\.` are treated literally with `-SimpleMatch`. False-negative FAIL verifications happened 3 times this session. Use `Python -m py_compile` and the actual file content as the truth source, not Select-String verifications alone.
4. **Don't paste PowerShell prompt prefixes into commands.** PowerShell tries to parse them and errors.
5. **Move-Item to a non-existent directory silently treats the directory name as a filename.** Caught this with the docs/ folder creation tonight.
6. **Stripe doesn't fire `checkout.session.completed` webhooks for $0 transactions.** EVIDENTIX100 (100% off) test purchases don't exercise the webhook code path. To test the webhook end-to-end, either generate a real charge or use Stripe's "Resend" feature on a previously-captured event.

---

## Session vibe note

This was a long session that hit multiple high points: webhook fix verified live, full landing page draft completed and locked, two SKUs cleanly retired, login crisis caught and resolved within minutes. **Tonight materially advanced the platform toward launch.** Next session can pick up from a state where the AI-sanctions copy is durable in git, the webhook is verifiably working, and the remaining blockers (SERVICE_MAP + Integrity Certificate sample + page HTML build) are well-defined.

End of memo.
