# Evidentix — AI-Sanctions Landing Page: Build Items

**Companion to:** `Evidentix_AI_Sanctions_Landing_Page_Draft.md`
**Status:** Copy complete (May 25, 2026). Implementation pending.
**Purpose:** Track all outstanding tasks required to ship the page to production.

---

## Pre-launch dependencies (must be done before page goes live)

### 1. Generate a real Integrity Certificate sample

**Why blocking:** Section 3 thumbnail and Section 8 "View full sample" CTA link to a sample Integrity Certificate. The current `/sample` route (or S3 PDF) returns a Custody Record, not an Integrity Certificate. Showing the wrong product on the landing page is a buyer-experience mismatch.

**Steps:**

1. Use a representative test file (a single image or short video that will not contain client data).
2. Generate a single-file Integrity Certificate via the production app (https://evidenceanalyzer.com).
3. Confirm the generated PDF shows the Integrity Certificate format (single-file forensic report), not the multi-file Custody Record format seen in today's `/sample` review.
4. Export the PDF.
5. Upload to S3 bucket `evidentix-files-ken01` (us-west-2) as the canonical sample. Suggested key: `samples/integrity_certificate_sample.pdf`. Set ACL to public-read.
6. Update or create the `/sample` redirect in `app/main.py` to point to the new S3 URL (or replace existing redirect target).
7. Verify the URL is reachable in an incognito browser session.

**Open question:** Should the `/sample` route also serve a redirect for `/sample/custody-record` and `/sample/monitoring` later, or stay single-purpose for now? Default: single-purpose; expand only if Custody Record and Monitoring get their own landing pages.

---

### 2. Confirm citation accuracy

**Why blocking:** Three footnotes carry legal-credibility weight. Wrong cite or stale cite undermines the whole page.

- **Footnote 1 (Mendones):** `Mendones v. Cushman & Wakefield, Inc., No. 23CV028772 (Cal. Super. Ct. Alameda Cnty. Sept. 9, 2025) (Kolakowski, J.).` Confirm docket number and judge's name verbatim against court records before launch.
- **Footnote 2 (Whiting):** Reporter cite was left as `[reporter cite]` placeholder in the draft. Pull the official cite — Federal Reporter volume/page if published, or "slip op." reference with docket if not yet in F.X. Confirm date precisely.
- **Footnote 3 (Liar's Dividend):** Citation to Delfino law review article is by name without volume/page. Pull full cite. NBC News reporting — link to a specific 2024 or 2025 article (or article series) rather than a generalized claim. Judicial Conference submissions — confirm the FRE 707 and Rule 901(c) reference is current and accurate.

---

### 3. Verify or finalize hero section copy

**Why noted:** The draft document carries Section 1 forward from May 6 with the headline locked but defers sub-elements ("sub-headline, lead paragraph framing, visual treatment") to the May 6 final draft. Confirm those sub-elements exist as a discrete record or reconstruct them. Without them, the build cannot start at Section 1.

---

## Build tasks (HTML/template work)

### 4. Build the HTML template

**Style guide:** Match the dark theme established for `login.html`, `register.html`, `compare.html`. Reference tokens:

- Page background: `#0f1117`
- Card surface: `#1a1d27`
- Card border: `#2d3148`
- Primary accent (brand purple): `#7c8cf8`
- Primary hover: `#6470e6`
- Body text: `#e2e8f0`
- Label text (muted): `#94a3b8`
- Hint/secondary: `#64748b`
- Font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

**Template considerations:**

- Should extend `base.html` for shared nav + footer (do not replicate the `compare.html` orphan pattern — that's flagged for separate rewrite).
- Eight sections require eight semantic `<section>` blocks. Each section's header, subhead, and body content rendered in consistent visual hierarchy.
- Section 2 sanctions cards: three-column grid on desktop, single-column stack on mobile.
- Section 4 scenarios: two-column grid on desktop, single-column stack on mobile.
- Section 5 steps: vertical sequence with numbered icons. Icons either inline SVG or a single icon font.
- Section 6 alternatives: three-column grid on desktop, single-column stack on mobile. Same visual rhythm as Section 2.
- Section 7 FAQ: expandable accordion preferred (uses native `<details>`/`<summary>` for accessibility) or static stacked Q+A.
- Section 8 CTA: large centered card with primary button. Button uses primary accent color, larger padding than standard buttons.

**Suggested file path:** `app/templates/ai_sanctions.html`

---

### 5. Wire the route

**Add to `app/main.py`:**

```python
@app.get("/ai-sanctions", response_class=HTMLResponse)
async def ai_sanctions_page(request: Request):
    return templates.TemplateResponse(
        request,
        "ai_sanctions.html",
        {"page_title": "Authenticate Your Digital Evidence — Evidentix"},
    )
```

**Open question:** Path choice. Options:

- `/ai-sanctions` — descriptive, signals what the page argues about
- `/integrity-certificate` — product-named, signals what the page sells
- `/litigators` — audience-named, segment-specific
- `/` — make it the homepage (replaces current `home.html`)

The May 25 decision committed to single-page Model C without specifying the URL. Default recommendation: `/ai-sanctions` because the page argues from the threat, and "integrity certificate" is a phrase the visitor doesn't know yet. Reconsider at build time.

---

### 6. SEO + meta tags

**Required for Google Ads landing-page approval:**

- `<title>` — under 60 chars
- `<meta name="description">` — under 160 chars, action-oriented
- `<meta property="og:title">` — for share previews
- `<meta property="og:description">`
- `<meta property="og:image">` — needs a separate 1200×630 social card image, brand-consistent
- `<link rel="canonical">` — point to the canonical URL

**Required for Google Ads quality score:**

- Contact information (footer link to `/contact` or visible operator address)
- Privacy Policy link (already published at `/privacy`)
- Terms of Use link (already published at `/terms`)
- Mobile responsiveness verified
- Page load under ~2.5 seconds (lighthouse / pagespeed test)

---

### 7. Analytics + conversion tracking

**Google Ads conversion ID is already live in the codebase:** `AW-18099032758`. The landing page must include the gtag conversion snippet so that "clicked the CTA" and "completed Stripe checkout" can be tracked back to the source ad campaign.

**Suggested events to track:**

- Page view (automatic via gtag)
- CTA button click (custom event)
- Section 7 FAQ expansion (engagement signal)
- Time on page (engagement signal)
- Scroll depth (engagement signal)

Open question: do you want a third-party analytics tool (Plausible, Fathom) added for privacy-first analytics, or stick with Google Ads + Render basic metrics? Stack decision pending.

---

### 8. End-to-end conversion test

**Why this is the launch gate:** A landing page that produces clicks but doesn't complete checkout is worse than no landing page. The full path must be verified before going live.

**Test path:**

1. Visit the landing page URL in incognito.
2. Click the primary CTA "Try one Certificate free."
3. Confirm redirect to `/pricing`.
4. Click the Integrity Certificate card's purchase button.
5. Confirm redirect to Stripe Checkout.
6. Confirm the "Add promotion code" link is visible.
7. Enter EVIDENTIX100. Confirm discount applies, total goes to $0.
8. Complete checkout (Stripe should not require a card on file at $0 — verified May 25, 2026).
9. Confirm redirect to `/success` page.
10. Run `python tools/audit_payments_subscriptions_20260525.py`. Confirm new Payment row with `product=integrity_certificate`, `amount_total=0`, `event_id` populated.
11. Verify the intake form renders (does NOT KeyError) when `service=integrity_certificate` is passed. **This is the critical risk.** See open item below.

---

## Critical risk to resolve before launch

### 9. SERVICE_MAP mismatch for `integrity_certificate`

**Why critical:** Per May 25 webhook investigation, the `intake_form` POST handler reads `SERVICE_MAP[service]` at `app/main.py:1432`. The current `SERVICE_MAP` has three entries: `single`, `comparison`, `investigation`. The `STRIPE_PRICES` dict and pricing page sell `integrity_certificate` (among others). When a buyer completes Stripe checkout for `integrity_certificate`, the post-checkout intake will raise `KeyError` on `SERVICE_MAP["integrity_certificate"]`.

**This means the landing page would convert successfully through Stripe but crash before the customer can use what they bought.**

**Two paths to resolve:**

**Path A — Build SERVICE_MAP entries for the brand SKUs.** Add `integrity_certificate` and `custody_record` entries to `SERVICE_MAP` with appropriate `name`, `price` (in cents), and `max_files` values. Verify the post-checkout intake flow handles these products end-to-end. This is the right answer if Integrity Certificate and Custody Record are staying.

**Path B — Refactor the intake handler to use `STRIPE_PRICES` / `PRICING` as source of truth.** Eliminates the dual-catalog problem entirely. Bigger change. The right answer if the goal is to retire the legacy `SERVICE_MAP` and consolidate around a single product catalog.

**The May 25 SKU lock work began this conversation but did not complete it.** The Firm License kill and the Professional Plan kill cleared the catalog of the obvious phantom products. The remaining seven one-time SKUs and three monitoring tiers all need this mismatch resolved before any of them can be sold on the landing page.

**Recommended order:**

1. Finish the SKU lock decision: which one-time products survive, which get retired.
2. Apply Path A or B for surviving products.
3. Verify the audit script shows clean Payment rows for at least the Integrity Certificate path.
4. **Then** ship the landing page.

---

## Post-launch tasks

### 10. CTA migration from EVIDENTIX100 to 14-day trial

**Background:** The May 25 decision was to launch the page with EVIDENTIX100 as the trial mechanic (Path B). The durable design (from the May 5 scoping session) is a 14-day full-platform trial.

**When the trial flow is built (Phase 1-4 of the May 5 scope, ~14-16 hours total across multiple sessions):**

1. Build a `/trial` or `/free-trial` route that signs the user up, marks the trial start on the `users` table, sends the Day 0 welcome email.
2. Update Section 8 CTA copy: header to `Try the Full Platform Free for 14 Days`, subhead removes EVIDENTIX100 reference, button to `Start your free trial`.
3. Update button target from `/pricing` to `/trial`.
4. Remove EVIDENTIX100 micro-copy.
5. Keep EVIDENTIX100 alive for cold outreach (it's already in the email templates and one-pagers).

### 11. Segment-specific landing pages (only if data justifies)

Per Model C: only build `/insurance-fraud-defense`, `/copyright-defense`, `/video-forensics` if Google Ads / conversion data shows a buyer segment converting differently or justifies dedicated spend per segment.

Don't build these speculatively.

### 12. Compare.html full rewrite

**Out of scope for landing page launch, but related:** `compare.html` was brand-patched (CSS-only) on May 25. The durable fix is rewriting it to extend `base.html`. If that rewrite happens before the AI-sanctions page launches, the template foundation will be cleaner.

---

## Estimated effort breakdown (rough)

| Task | Hours |
|---|---|
| 1. Generate real Integrity Certificate sample | 0.5 |
| 2. Confirm citations | 1.0 |
| 3. Verify hero section copy | 0.5 |
| 4. Build HTML template | 6-10 |
| 5. Wire route | 0.5 |
| 6. SEO + meta tags + social card image | 2.0 |
| 7. Analytics + conversion tracking | 1.5 |
| 8. End-to-end conversion test | 1.0 |
| 9. SERVICE_MAP fix (Path A, narrow scope) | 2.0 |
| **Pre-launch total** | **~15-19 hours** |
| 10. CTA migration to 14-day trial (post-launch) | 14-16 |

---

## Suggested launch sequence

1. **Session A (~3 hours):** Items 1, 2, 3, 9. Pre-launch verifications and the SERVICE_MAP fix. The page cannot ship until the intake flow doesn't crash.
2. **Session B (~6-8 hours):** Item 4. Build the HTML template.
3. **Session C (~4 hours):** Items 5, 6, 7, 8. Wire route, meta tags, analytics, end-to-end test.
4. **Launch.**
5. **Future sessions:** Item 10 (trial migration), Items 11-12 (optional follow-ups).

---

## Open strategic questions (to revisit at build time, not blocking)

- Final URL path (default: `/ai-sanctions`)
- Whether Section 7 FAQs are accordion or static stacked
- Whether `og:image` social card design is custom or uses an existing brand asset
- Privacy-first analytics layer (Plausible, Fathom) added or not
- Whether the existing `home.html` becomes obsolete once `/ai-sanctions` is live, or whether both coexist
