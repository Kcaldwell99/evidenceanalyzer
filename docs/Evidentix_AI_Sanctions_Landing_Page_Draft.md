# Evidentix — AI-Sanctions Landing Page

**Status:** Copy complete. All eight sections locked.
**Date locked:** May 25, 2026
**Mechanic:** EVIDENTIX100 promo code at /pricing checkout (path B from May 25 decision)
**Future migration:** Replace CTA mechanic with 14-day trial when trial flow is built (~14-16 hr build, deferred)

**Strategic frame (locked in May 6 session, reaffirmed May 25):**

- Page job: conversion. Drive trial Integrity Certificate signups.
- Audience: practicing litigators, both defensive (authenticating own evidence) and offensive (rebutting deepfake objections).
- Anchor case: *Mendones v. Cushman & Wakefield* (Cal. Super. Ct. Sept. 2025) — terminating sanctions for AI-fabricated exhibits.
- Page sells only Integrity Certificate. Not Custody Record. Not Monitoring.
- Single landing page for all four buyer segments (Generalist Litigators, PI/Insurance, Video Forensics, Copyright). PDF one-pagers serve segment-specific cold outreach.
- Author/operator stays anonymous ("attorney-built," not Kenneth-named).
- No testimonials, no logo bars. Citations as footnotes, not hyperlinks.

---

## Section 1 — Hero

**Headline:** Every digital exhibit you file is now challengeable as AI-generated. Here's how you prove it isn't.

*(Section 1 was drafted and locked in the May 6 session; copy carried forward as-is. Sub-elements like sub-headline, lead-paragraph framing, and any visual treatment are owned by Section 1 final draft.)*

---

## Section 2 — Sanctions Wall

**Header:** The Sanctions Are Already Falling

**Layout:** Three cards.

### Card 1 — Mendones

*Terminating sanctions for AI-fabricated exhibits.*

In September 2025, a California Superior Court dismissed a housing case with prejudice after the plaintiffs filed exhibits — videos, ring-cam stills, messaging screenshots — that the court identified as AI-generated. The metadata claimed an iPhone 6 Plus running iOS 12.5.5; the AI features visible in the footage required an iPhone 15 Pro running iOS 18. The court rejected monetary sanctions as insufficient, rejected evidence sanctions as insufficient, and entered terminating sanctions under Cal. Code Civ. Proc. § 128.7(b).¹

### Card 2 — Whiting

*$30,000 appellate sanctions for fabricated case citations.*

In March 2026, the Sixth Circuit imposed $30,000 in sanctions on an attorney who submitted a brief containing AI-hallucinated case citations — eleven non-existent cases used to support arguments on appeal. The panel said that smaller sanctions had "plainly been inadequate" to deter the conduct, and that escalation was now warranted.²

### Card 3 — The Liar's Dividend

*Authentic evidence challenged as AI-generated.*

The mirror problem is now visible in trial courts: real evidence is being attacked as fabricated. Witnesses claim their actual statements were AI-generated. Defendants argue authentic surveillance footage was deepfaked. The phenomenon has been documented by NBC News reporting, by the Delfino law review article, and by submissions to the Judicial Conference Advisory Committee on Evidence Rules. The challenge is no longer hypothetical.³

**Footnotes:**

1. *Mendones v. Cushman & Wakefield, Inc.*, No. 23CV028772 (Cal. Super. Ct. Alameda Cnty. Sept. 9, 2025) (Kolakowski, J.).
2. *Whiting v. City of Athens*, [reporter cite] (6th Cir. March 2026).
3. NBC News investigative reporting on deepfake denial defenses (2024–2025); Rebecca Delfino, *Deepfake Evidence in Court*, [law review cite]; submissions to the Judicial Conference Advisory Committee on Evidence Rules on FRE 707 and proposed Rule 901(c) amendment.

**Closing block (centered, italicized below the three cards):**

The era of $5,000 warnings is over.

*You cannot control what opposing counsel argues. You can control whether your evidence survives the argument.*

---

## Section 3 — The Integrity Certificate

**Header:** What an Integrity Certificate Is

**Subhead:** *A documented forensic snapshot of your digital evidence at the moment of filing.*

**Lead paragraph:**

The Integrity Certificate is a PDF report generated the moment you upload a digital exhibit. It captures the file's cryptographic fingerprint, embedded provenance data, metadata, and forensic indicators — then preserves all of it in a court-ready document with a chain-of-custody log. When opposing counsel raises an AI-generation challenge, you have a contemporaneous, third-party-generated record that says: here is what this file was, the moment it entered the record.

**[Thumbnail of sample Integrity Certificate, right-aligned or centered. Caption beneath: "Sample Integrity Certificate — click to view full PDF"]**

*Note for build: current /sample route returns a Custody Record, not an Integrity Certificate. A real Integrity Certificate sample needs to be generated and hosted before launch. See open build items document.*

**What it contains:**

- **SHA-256 cryptographic hash** of the file, computed at upload, recorded immutably
- **C2PA manifest validation** when present, including trust-list verification and revocation checking
- **Embedded metadata extraction** — EXIF, GPS coordinates, device identifiers, software signatures
- **AI provenance flags** — when a file carries C2PA credentials indicating AI generation or AI assistance, those are surfaced and validated against the issuing authority's trust list
- **File integrity verification** — comparison against any prior versions in your case
- **Hash-chained custody log** — every access, every action, every timestamp, cryptographically linked

**What it does not claim:**

The Certificate does not declare a file authentic or fabricated. It documents what the file contains and what forensic analysis revealed at the moment of capture. The conclusion — admissibility, authentication, weight — remains with the court. The Certificate's value is that it preserves the evidence trail before challenge, in a form that survives cross-examination.

**Closing line (transitional to Section 4):**

*That's the product. Here's how litigators actually use it.*

---

## Section 4 — How Litigators Use It

**Header:** Two Scenarios

**Subhead:** *Whether you're presenting the exhibit or challenging it.*

**Layout:** Two side-by-side cards.

### Card A — When you're filing

**Title:** Pre-emptive Authentication

A PI carrier is defending a $4M staged-accident claim. The plaintiff has produced a dash-cam video that appears to show the carrier's insured running a red light. The carrier's litigator suspects the video is doctored — frame-rate anomalies, lighting inconsistencies — but is also relying on its own surveillance footage from the intersection, captured by a nearby business.

Before filing the surveillance video in opposition to summary judgment, the litigator generates an Integrity Certificate at upload. The Certificate records the file's cryptographic hash, original camera metadata, GPS coordinates, and C2PA provenance. When opposing counsel inevitably challenges the surveillance video as "AI-enhanced" or "generative," the carrier's response is not a denial — it's a contemporaneous, third-party-generated record that documents exactly what the file was the moment it entered the litigation.

### Card B — When you're challenging

**Title:** Forensic Counter-Authentication

A copyright plaintiff has filed a § 512(f) misrepresentation claim. The defendant's DMCA takedown notice attached screenshots purporting to show the plaintiff's infringing use — but the screenshots show an iOS version that didn't exist on the date stamped in the metadata, and the device identifier suggests a model released after the alleged infringement.

The plaintiff's litigator runs the defendant's screenshots through Evidentix, generating an Integrity Certificate that surfaces the metadata contradictions, the absent C2PA provenance, and the file's complete EXIF history. The Certificate becomes Exhibit B to the plaintiff's motion for sanctions — not as a conclusion that the screenshots are fabricated, but as a documented forensic record that the screenshots cannot be what the defendant claims.

**Closing line (transitional to Section 5):**

*The Certificate is the same in both directions. Here's what happens when you upload a file.*

---

## Section 5 — How It Works

**Header:** From File to Certificate

**Subhead:** *Three steps. Minutes, not hours.*

**Layout:** Three numbered steps with simple icons (upload arrow, magnifying glass, document).

### 1. Upload your file

You upload the digital exhibit through your Evidentix account — image, video, or PDF. The file is hashed at the moment of upload, recording its SHA-256 fingerprint before anything else happens. The original file is preserved unaltered; all analysis runs on a working copy.

### 2. Forensic analysis runs automatically

Evidentix extracts the file's embedded metadata, validates any C2PA manifests against the issuing authority's trust list, captures EXIF and GPS data, and compares the file against any prior versions in your case. Every action is recorded in a hash-chained custody log — each row cryptographically linked to the one before it.

### 3. Integrity Certificate is generated

The analysis is rendered into a court-ready PDF report. You download it, attach it to your filing, or hold it in your case file in anticipation of a future challenge. The Certificate is timestamped and verifiable against the original file at any later date — any change to the file would produce a different hash and break the chain.

**Closing line (transitional to Section 6):**

*That's the workflow. Here's why we built it this way — and how it compares to what else is out there.*

---

## Section 6 — Why Evidentix

**Header:** What Else Could You Do?

**Subhead:** *Three alternatives. None of them solve the same problem.*

**Layout:** Three columns.

### Card 1 — Do Nothing

**Subtitle:** File the exhibit as-is. Hope the challenge doesn't come.

The path of least resistance. Most litigators have always done it this way. The exhibit goes in the record without a forensic trail, and the assumption is that opposing counsel won't raise an AI-generation challenge — or that if they do, you'll handle it then.

**The problem:** *Mendones* shows what happens when "we'll handle it then" arrives too late. Once a judge has read the motion accusing your client's evidence of being fabricated, the question is no longer whether you can prove authenticity. It's whether you preserved the evidence trail before the doubt was raised. There is no contemporaneous forensic record to produce. The trail was never built.

**How Evidentix differs:** The Certificate is generated at the moment of upload, before any challenge exists. It is the contemporaneous record, made before the dispute. By the time opposing counsel raises the AI argument, your documentation is already in your case file — timestamped, hash-verified, and dated weeks or months earlier.

### Card 2 — Hire a Forensic Expert

**Subtitle:** $5,000–$50,000. Three to eight weeks. Per case.

The traditional answer. A retained digital forensics expert produces a report, often with deposition testimony. The work is rigorous, the credentials are real, and the cost reflects both.

**The problem:** Expert engagements are scoped to cases that already have a known fight. They are reactive, not preventive — the expert is retained after opposing counsel has signaled the challenge, which means the analysis happens after the evidence has already entered the record without forensic baseline. The cost also forecloses use on smaller matters where the exposure doesn't justify a $20,000 expert but the embarrassment of a fabrication argument is still real.

**How Evidentix differs:** At $49 per Certificate, authentication becomes a workflow step, not a budgetary decision. Every file gets the forensic baseline. The expert remains available for the matters that require trial testimony — the Certificate handles the documentation gap that exists in every other case.

### Card 3 — Use Free Tools

**Subtitle:** ExifTool. JPEGsnoop. Online metadata readers.

Some litigators run their own forensic analysis using free or low-cost utilities. The technical skill exists; the tools exist; the data is there for anyone who knows where to look.

**The problem:** Three gaps. First, the output is not court-ready — raw metadata dumps and command-line output are not exhibit format. Second, there is no chain of custody, no hash-chained log, no documented forensic timeline. The fact that an attorney looked at a file's EXIF data on a personal laptop in 2024 does not establish anything in 2026. Third, the analysis is partial — generic metadata readers do not validate C2PA manifests against trust lists, do not perform cross-file comparison, and do not produce a single integrated record.

**How Evidentix differs:** The Certificate is a third-party-generated, timestamped, court-ready PDF with a complete custody log. Where a free tool produces a partial answer and no documentation, Evidentix produces the integrated forensic record in a form that survives a motion in limine.

**Closing line (transitional to Section 7):**

*Common questions before you try one.*

---

## Section 7 — Common Questions

**Header:** Before You Try One

**Layout:** Six expandable Q+A items (or as static stacked items, depending on visual treatment chosen at build time).

### Q: Will an Integrity Certificate be admissible in my jurisdiction?

The Certificate is not admitted by virtue of being an Evidentix product. It is admitted the way any business record or contemporaneous forensic documentation is admitted — through the foundation an attorney lays for it. The Certificate is designed to meet that foundation: it is generated by an automated forensic process, timestamped at the moment of file ingest, preserved unaltered, and accompanied by a hash-chained custody log. Federal Rules of Evidence 803(6), 901(b)(4), and 901(b)(9) — and their state-law analogs — provide the framework. Evidentix produces the documentation; you make the foundational case.

### Q: Who is Evidentix? Why should I trust this report?

Evidentix is built and operated by a practicing litigator who recognized that digital evidence authentication had no defensible, repeatable workflow at the case-management level. The platform exists because no other product produces a court-ready forensic record at the moment of ingest, with chain-of-custody preservation, at a price that lets every exhibit be authenticated rather than only the high-stakes ones. The Certificate's value is not the brand on the report — it is the integrated forensic record, the hash-chained custody log, and the timestamp that establishes when the file's state was captured. Those elements are inspectable, verifiable, and reproducible.

### Q: What happens if I need to testify about the Certificate?

You can. The Certificate documents what was extracted from the file, when, and by what process — all of which is straightforward to describe under oath. You testify to the workflow ("I uploaded the file on this date, the platform generated the Certificate, I attached it to the filing"), not to the underlying forensic science. The custody log inside the Certificate establishes the chronology. For matters that require expert testimony about *what the forensic findings mean*, a retained expert remains appropriate; the Certificate is the documentation foundation that expert work is built on.

### Q: Does using Evidentix open me up to discovery of the underlying file or analysis?

The file you upload is your client's file, subject to your existing discovery and privilege analysis. Evidentix does not change what is discoverable. The Certificate itself is a documented forensic record of a file you already possess — the same forensic analysis a free tool would produce, in a court-ready form. If the file is discoverable, it is discoverable whether or not you ran it through Evidentix; if the Certificate is responsive to a discovery request, that is a question for the underlying file, not for the documentation about it.

### Q: I file dozens of exhibits a year. Is this $49 per file?

Per-file pricing scales linearly, and for some practices that is the right answer — the Certificate is the documentation step in a workflow you'd run anyway. For litigators handling higher volumes, Evidentix offers Custody Monitoring subscriptions ($49 / $99 / $199 per month) that cover ongoing monitoring of larger evidence sets across an entire matter or portfolio. Most users start with one Certificate, confirm the workflow fit, and move into monitoring when volume justifies it.

### Q: Does Evidentix retain copies of my client's files?

Files uploaded for Certificate generation are stored on Evidentix infrastructure to preserve the chain-of-custody record that the Certificate references. Files are accessed only by you and your authorized account users. Storage is encrypted at rest, transmission is encrypted in transit, and retention is governed by Evidentix's published Privacy Policy. If your matter requires deletion of the file at a defined point — for example, after final disposition — that request is honored through your account.

**Closing line (transitional to Section 8):**

*Ready to try one?*

---

## Section 8 — Final CTA

**Header:** Authenticate Your First Exhibit. Free.

**Subhead:** *Use code EVIDENTIX100 at checkout. One Certificate, no charge, no card required.*

**Body paragraph:**

Every digital exhibit you file is now challengeable as AI-generated. Mendones is the proof; the era of $5,000 warnings is over. The Integrity Certificate is the contemporaneous forensic record that documents what your evidence was — the moment it entered the litigation. Run one through the platform. See what it produces. Decide from there.

**Primary button:** **Try one Certificate free**

*Button target: /pricing (Integrity Certificate card → checkout → manual EVIDENTIX100 entry)*

**Button micro-copy beneath button:** *Use code EVIDENTIX100 at checkout.*

**Secondary link:** *Already a subscriber? Sign in →*

*Secondary link target: /login*

---

## Footnotes and citations (consolidated)

1. *Mendones v. Cushman & Wakefield, Inc.*, No. 23CV028772 (Cal. Super. Ct. Alameda Cnty. Sept. 9, 2025) (Kolakowski, J.).
2. *Whiting v. City of Athens*, [confirm reporter cite at build time] (6th Cir. March 2026).
3. NBC News investigative reporting on deepfake denial defenses (2024–2025); Rebecca Delfino, *Deepfake Evidence in Court*, [confirm law review cite at build time]; submissions to the Judicial Conference Advisory Committee on Evidence Rules on FRE 707 and proposed Rule 901(c) amendment.

---

## Build notes carried forward

- Single page targeting general litigators with broad hero copy. Segment-specific landing pages (`/insurance-fraud-defense`, `/copyright-defense`, `/video-forensics`) only built later if Google Ads / conversion data justifies dedicated spend per segment.
- PDF one-pagers continue serving segment-specific cold outreach. Not replaced by the landing page.
- Page must launch with Privacy Policy + TOS + Subpoena Policy already live (they are, as of May 23, 2026).
- See companion build-items document for outstanding implementation tasks (Integrity Certificate sample generation, HTML template, route wiring, SEO meta tags, end-to-end conversion test).
