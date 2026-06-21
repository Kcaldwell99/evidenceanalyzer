# 3b + 3c Build Draft -- Integrity Cert Paywall (Path 2, Option B)
# Drafted June 20 2026, session 2. NOT YET APPLIED. Design locked; two items open.

## Locked decisions
- Path 2: generate-first. User clicks generate -> gate -> unpaid redirects to checkout -> pay -> auto-generate.
- Option B: NO refactor of the generate route. /success redirects BACK into generation
  (which now passes the gate because the Payment row exists). One generation code path.
- 3c-i: reuse assert_cert_entitlement as-is; CATCH its HTTPException(402) and convert to redirect.

## Already done (session 2, local, compile-clean, NOT deployed)
- 3a: /checkout/{product} takes optional case_id/evidence_id, stamps metadata{product,user_id,case_id,evidence_id}.
- 3a: webhook reads metadata, stamps Payment.user_id/case_id/evidence_id.
- entitlements.py: assert_cert_entitlement written, compile-verified, NOT wired.
- migration a3f1d9c2b8e4: APPLIED to prod (3 cols + indexes on payments).

## The three changes to apply (Option B)

### Change 1 (3c) -- gate + redirect in generate route
Location: main.py, /generate/integrity/{case_id}/{evidence_id} (route starts ~1891),
insert RIGHT AFTER the `if not item: raise HTTPException(404 ...)` block,
BEFORE `# Load report data`.

    from app.entitlements import assert_cert_entitlement
    from fastapi import HTTPException as _HTTPExc
    from urllib.parse import quote
    try:
        assert_cert_entitlement(db, current_user, case_id, evidence_id)
    except _HTTPExc as e:
        if e.status_code == 402:
            return RedirectResponse(
                url=("/checkout/integrity_certificate"
                     f"?case_id={quote(case_id)}&evidence_id={quote(evidence_id)}"),
                status_code=303,
            )
        raise

Ordering rationale: ownership/existence 404s come FIRST (don't reveal pricing on a
file you don't own), THEN entitlement.

### Change 2 (3b-part-1) -- checkout threads file ids into success_url
Location: main.py checkout route, the success_url= line (~1675).
Current:
    success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}&product={product}",
Change to (only appends file ids when present, so generic/subscription checkouts unchanged):
    success_url=(
        f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}&product={product}"
        + (f"&case_id={quote(case_id)}&evidence_id={quote(evidence_id)}"
           if case_id and evidence_id else "")
    ),
Requires `from urllib.parse import quote` in scope (add at top of route or module).

## OPEN ITEM 1 (MUST resolve before applying) -- POST vs GET redirect-back
The generate route is @app.post. A 303 redirect from /success (a GET page) becomes a GET,
which a POST-only route will NOT serve. So Change 3 cannot simply 303 to the generate route.
Candidate solutions -- evaluate against the actual route:
  (a) Add GET support to the generate route (@app.api_route(..., methods=["GET","POST"])).
      Simplest, but verify nothing relies on POST-only (CSRF? form-only assumptions?).
  (b) Extract generation into a helper after all (this is the Option A refactor we avoided;
      fall back only if GET-enabling is unsafe).
  (c) /success page auto-submits a hidden POST form to the generate route via JS.
      No route change, but adds a client-side step and a flash of the success page.
  Recommended to evaluate (a) first. Needs: read the REST of the generate route
  (past line ~2000 -- PDF upload + Certificate row write, NOT yet seen) to confirm a GET
  re-entry is side-effect-safe (note: re-hitting generate after the cert row exists hits
  branch 2 of the gate = free re-gen, so re-entry is safe).

## Change 3 (3b-part-2) -- /success redirects back to generate for file certs
Location: main.py /success route (~1665). DEPENDS ON OPEN ITEM 1.
- Add params: case_id: str = "", evidence_id: str = ""
- Add `db: Session = Depends(get_db)` (route currently has NO db dependency).
- If case_id and evidence_id present: route the user back into generation
  (mechanism per OPEN ITEM 1), which now passes the gate.

## OPEN ITEM 2 (MUST resolve before applying) -- deploy path
- Render CLI token dead since 5/14. Unknown if Render auto-deploys / runs alembic upgrade head.
- The next deploy carries the 3a webhook change. A deploy fault there silently breaks
  recording of REAL payments. Refresh token + confirm deploy path BEFORE pushing anything.

## Still must read next session (no writes today)
- main.py generate route from ~line 2000 to its end: PDF upload, Certificate row write,
  what it RETURNS on success (Change 3 / OPEN ITEM 1 depend on this).
- case_detail.html:279 form -- confirm plain POST (it is: method="post"); UX of redirect chain.

## 3d (after 3b/3c) -- disable generic integrity buy buttons
- ai_sanctions.html:56, pricing.html:66, upload.html:478 -- integrity SKU buy with no file
  produces an unmatchable Payment. Disable/redirect for integrity specifically; leave other SKUs.

## Step 4 -- three-way prod acceptance test (after wiring, after deploy)
- non-payer clicks generate -> redirected to checkout (not bare 402)
- payer completes checkout -> /success -> cert generates
- re-download of already-paid cert -> free (gate branch 2)