# CLAUDE.md — Evidentix / Evidence Analyzer

Guidance for Claude Code working in this repository. Read this fully before editing, running code, or touching the database.

---

## ⚠️ CRITICAL: the local `.env` points at PRODUCTION Postgres

There is **no local database.** The `DATABASE_URL` in `.env` connects to the live Render production Postgres. This means:

- **Every `alembic upgrade head` is a live production migration.** Never run one casually.
- Any script that writes to the DB writes to **production.** Default to read-only (`SELECT`) when investigating.
- Before running anything that mutates data, stop and confirm intent explicitly with the user.
- Treat destructive operations (DELETE, UPDATE, DROP, migrations) as requiring sign-off, not as routine.

This is the single most damaging thing to forget.

---

## Project overview

Evidentix is a digital-evidence-authentication SaaS operated by **Evidence Analyzer, LLC** (TX). It sells three SKUs: Integrity Certificate ($99), Custody Record ($199), Custody Monitoring (subscription).

- **Backend:** FastAPI / Python on Render (auto-deploys from the `main` branch).
- **DB:** PostgreSQL (Render-hosted; see warning above).
- **Storage:** AWS S3, bucket `evidentix-files-ken01` (us-west-2), per-object public-read ACLs.
- **Payments:** Stripe (regular Checkout, single-seller). Operating entity Evidence Analyzer, LLC.
- **Other:** Resend (email), Google Vision (web detection), Google Ads conversion tracking (ID `AW-18099032758`, fires on checkout-success only).
- **Frontend:** server-rendered Jinja2 templates + a single hand-written `/static/css/main.css` (CSS custom properties, `--brand-purple-*` palette). No JS framework, no build step. `home.html` is standalone (does not extend base).

---

## Git & deploy flow

- GitHub: `Kcaldwell99/evidenceanalyzer`. Local: `C:\Users\kcald\c2pa-evidence-mvp\` (Windows).
- Push pattern: **`git push origin dev`** then **`git push origin dev:main`** (the second triggers the Render deploy).
- **No `$` in commit messages** (PowerShell escaping breaks them). Match on safe substrings.
- Use **`git add -f`** for new files when needed.
- Backend changes have no visible page to verify; confirm via behavior/logs after deploy.

---

## Editing conventions

- Make **surgical, exact-match edits.** Before replacing, verify the anchor is unique (`s.count(OLD) == 1`); abort if not.
- For scripted edits, use throwaway scripts under **`_scratch/`** (gitignored). Pattern: ReadAllText → uniqueness guard → backup (`.bak`) → edit → verify → write.
- Write files as **UTF-8 with NO BOM.** (A BOM on `.env` previously broke `load_dotenv` and every local script — don't reintroduce one anywhere.)
- **Line endings vary by file.** Some templates are LF; `app/utils/image_fingerprint.py` is CRLF. Anchors that span newlines must match the file's actual endings — prefer **single-line anchors**, or detect the newline (`nl = "\r\n" if "\r\n" in s else "\n"`) and build replacements with it.
- Run **`python -m py_compile`** on touched Python before committing, and smoke-test imports where practical.
- Reusable cert test harness lives at `_scratch/test_cert_section3.py` (regenerates a synthetic cert; write to a fresh filename to avoid file locks if a PDF is open in a viewer).

---

## Domain rules that must not be violated

**Custody log is a hash-chained audit trail.** `app/utils/audit_log.py` computes each row's `chain_hash` as SHA-256 over the prior hash plus the event content (which **includes `evidence_id`**).

- **NEVER backfill or edit `evidence_id` (or any content field) on existing `custody_log` rows.** Doing so breaks chain verification — which is the entire defensibility proposition of the product. Null `evidence_id` on access/deletion/case-level events (file_viewed, custody_record_generated, evidence_deleted, case_deleted, comparison_performed) is **correct**, not a bug.
- `verify_chain(case_id)` returns `(True, None, None)` when intact, or `(False, row_id, msg)` at the first break. Use it to confirm integrity; never to justify rewriting history.

**Conversion tag scope.** The Google Ads tag (`AW-18099032758`) is intentionally on the **checkout-success page only**, consent-gated, as promised in the Privacy Policy (section 3.9) and cookie docs. **Do not add it site-wide** — that would contradict the posted privacy promise.

**Overclaiming discipline.** Deliverables are positioned as **"exhibit-ready," not "court-ready"/"trial-ready."** Certificates document technical facts (hash, metadata, provenance) and explicitly do **not** assert admissibility — that's the court's call. Keep this guardrail in any user-facing copy.

**Compliance posture ("Version B").** Marketing presents Evidentix as a **software product, not legal services.** Do not add "practicing litigator / attorney" credibility hooks to user-facing pages; keep the non-legal-services / no-attorney-client disclaimer prominent. This keeps the site out of attorney-advertising rules across MO/KS/TX/CO/NV.

**⚠️ C2PA removed from the Integrity Certificate — MUST be restored, do not let this be silently lost.** When §4 of the cert became **Chain of Custody**, the prior **§4 Content Credentials (C2PA) Analysis** display was removed from `pdf_integrity_certificate.py`. The data is **not** lost: `report['c2pa']` is still built in `app/main.py` and C2PA is still rendered in the **Custody Record** (`pdf_custody_record.py`). But the **Integrity Certificate no longer shows C2PA.** C2PA must be **restored to the cert as part of the §5 Content Analysis redesign** — reframed as **probabilistic** with **FRE 707** (expert-opinion) caveats, not presented as a deterministic verification.

**⚠️ C2PA trust anchors are NOT configured — every signed file renders INVALID ("Verification Failed").** The c2pa Reader is called with **no trust settings** (`app/c2pa_analysis.py:159`), so c2pa-rs marks **every** signing cert `untrusted` by default → `trust_list_status='untrusted'` → `_determine_state` (line 340) renders **INVALID**. **CONSEQUENCE:** in production, any genuinely C2PA-signed file (valid signature, trusted timestamp, not revoked) currently renders as C2PA **"Verification Failed"** in the Integrity Certificate — **good evidence flagged as bad.** The **VALID branch is structurally unreachable** until trust anchors are loaded. This is a **product-correctness issue**, not just a sample-sourcing blocker. **OPEN DECISION:** which trust list to load, **AND** how "valid signature / untrusted issuer" should render (likely a **distinct state**, not collapsed into "Verification Failed" — has **Sedona / FRE calibration** implications). Also: the public **`/sample`** is still **stale** (old pre-redesign cert); a refreshed sample is **blocked on this trust decision.**

---

## Key files

- `app/main.py` — routes, `STRIPE_PRICES`, `PRICING`.
- `app/analyzer.py` — `analyze_file`, produces the stored S3 `json_report` blob (exif, gps_coords, phash, methodology, limitations).
- `app/pdf_integrity_certificate.py` — `generate_integrity_certificate(...)`, the $99 deliverable (Platypus/flowable PDF). Sections §1–§7: §1 Identification & Scope, §2 Cryptographic Integrity, §3 Captured Metadata, §4 Chain of Custody, §5 Content Analysis [C2PA restoration pending — see guardrail above], §6 Methodology, §7 Limitations & Disclaimers.
- `app/utils/image_fingerprint.py` — `generate_phash` (PDF detection by %PDF magic bytes + extension).
- `app/utils/audit_log.py` — `_compute_chain_hash`, `verify_chain` (hash-chained custody).
- `app/utils/map_render.py`, `app/utils/geocode.py` — GPS map + reverse-geocode for cert section 3.
- `app/models.py` — SQLAlchemy models (User, Case, EvidenceItem, FingerprintIndex, Payment, Subscription, CustodyLog, Certificate).
- `app/templates/ai_sanctions.html` — PPC landing page (Version B posture, has the disclaimer).

---

## Working style

Terse, incremental ("baby steps"): one action, confirm, proceed. The user writes all product decisions, legal copy, and GTM strategy; Claude assists with code, structure, research, and drafting. Surgical edits over sweeping rewrites.