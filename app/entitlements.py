"""Entitlement gate for Integrity Certificate generation.

Standalone module: imports only models and FastAPI's HTTPException, so it has
no dependency on app.main and can be unit-tested in isolation.

The single public function, assert_cert_entitlement, decides whether a caller
may generate an Integrity Certificate for one specific file. It is a guard:
it returns None when entitled and raises HTTPException(402) when not.

NOTE: This function is NOT yet wired into the /generate/integrity route. Branch
3 (paid Payment) cannot match until the checkout/webhook stamps user_id,
case_id, and evidence_id onto Payment rows (a later build step). Wiring this in
before that step would 402 paying customers.
"""
from fastapi import HTTPException

from app.models import Certificate, Payment


def assert_cert_entitlement(db, current_user, case_id, evidence_id):
    """Gate Integrity Certificate generation for one specific file.

    Branch order (first match wins):
      1. Admin bypass             -> allowed
      2. Cert already exists for   -> allowed (free re-gen; a certificates row
         this exact file              is written only after a successful, paid
                                      generation, so its existence authorizes
                                      re-download)
      3. A paid, file-specific     -> allowed (first paid generation)
         Payment exists
      4. otherwise                 -> raise HTTPException(402)

    File identity is the (case_id, evidence_id) string pair. Branch 2 is
    file-scoped (any owner of the file re-gens free). Branch 3 additionally
    scopes to current_user.id and product, and takes a row lock (FOR UPDATE)
    to serialize concurrent generate attempts against a single payment.

    Returns None when entitled; raises HTTPException(status_code=402) otherwise.
    """
    # Branch 1: admin bypass
    if getattr(current_user, "is_admin", False):
        return

    # Branch 2: an integrity cert already exists for this file -> free re-gen.
    existing_cert = (
        db.query(Certificate)
        .filter(
            Certificate.type == "integrity",
            Certificate.case_id == case_id,
            Certificate.evidence_id == evidence_id,
        )
        .first()
    )
    if existing_cert is not None:
        return

    # Branch 3: a paid, file-specific Payment exists -> allowed (first gen).
    # with_for_update() serializes concurrent generate calls for the same file.
    paid_payment = (
        db.query(Payment)
        .filter(
            Payment.user_id == current_user.id,
            Payment.case_id == case_id,
            Payment.evidence_id == evidence_id,
            Payment.product == "integrity_certificate",
            Payment.status == "paid",
        )
        .with_for_update()
        .first()
    )
    if paid_payment is not None:
        return

    # Branch 4: not entitled.
    raise HTTPException(
        status_code=402,
        detail="Payment required to generate this Integrity Certificate.",
    )

def assert_compare_entitlement(db, current_user):
    """Gate comparison runs (credit model).

    Admin bypass; otherwise require a paid, unconsumed comparison Payment
    for this user. Returns the locked Payment row so the caller can consume
    it after a successful run; returns None for admins.
    Raises HTTPException(402) when no credit is available.
    """
    if getattr(current_user, "is_admin", False):
        return None
    credit = (
        db.query(Payment)
        .filter(
            Payment.user_id == current_user.id,
            Payment.product == "comparison",
            Payment.status == "paid",
            Payment.consumed_at.is_(None),
        )
        .order_by(Payment.id)
        .with_for_update()
        .first()
    )
    if credit is None:
        raise HTTPException(
            status_code=402,
            detail="Payment required: purchase a Comparison Report to run this analysis.",
        )
    return credit


def consume_compare_credit(db, credit):
    """Stamp a comparison credit as spent. No-op for admin runs (credit=None)."""
    if credit is None:
        return
    from datetime import datetime, timezone
    credit.consumed_at = datetime.now(timezone.utc)
    db.commit()
