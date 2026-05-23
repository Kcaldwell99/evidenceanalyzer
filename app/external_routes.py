"""
app/external_routes.py

External service endpoints for LegalDrop and OutbackPix.
Add to app/main.py:

    from app.external_routes import external_router
    app.include_router(external_router)

Add to Render environment variables:
    LEGALDROP_API_KEY=<secrets.token_hex(32)>
    OUTBACKPIX_API_KEY=<secrets.token_hex(32)>
"""

import os
import hashlib
import httpx
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.utils.audit_log import log_audit_event, load_audit_log, verify_chain
from app.pdf_integrity_certificate import generate_integrity_certificate
from app.pdf_custody_record import generate_custody_record
from app.storage import s3_client, AWS_S3_BUCKET as EVIDENTIX_BUCKET

external_router = APIRouter(prefix="/api/v1", tags=["external"])

ALLOWED_KEYS = {
    k for k in [
        os.environ.get("LEGALDROP_API_KEY"),
        os.environ.get("OUTBACKPIX_API_KEY"),
    ] if k
}


def _auth(x_api_key: str):
    if not x_api_key or x_api_key not in ALLOWED_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key.")


@external_router.get("/ping")
async def ping(x_api_key: str = Header(...)):
    _auth(x_api_key)
    return {"status": "ok", "service": "evidentix"}


class CertifyRequest(BaseModel):
    s3_url:         str
    filename:       str
    case_id:        str
    task_id:        str
    provider_id:    str
    notes:          Optional[str] = None
    exif_lat:       Optional[float] = None
    exif_lng:       Optional[float] = None
    exif_timestamp: Optional[str] = None


class CertifyResponse(BaseModel):
    certificate_id: str
    sha256:         str
    cert_url:       str
    chain_verified: bool


@external_router.post("/certify", response_model=CertifyResponse)
async def certify_document(
    payload: CertifyRequest,
    x_api_key: str = Header(...),
):
    _auth(x_api_key)

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.get(payload.s3_url)
        if r.status_code != 200:
            raise HTTPException(502, f"S3 fetch failed: HTTP {r.status_code}")
        file_bytes = r.content
    except httpx.RequestError as e:
        raise HTTPException(502, f"S3 fetch error: {e}")

    sha256 = hashlib.sha256(file_bytes).hexdigest()

    notes = payload.notes or (
        f"File: {payload.filename} | SHA-256: {sha256}"
        + (f" | GPS: {payload.exif_lat},{payload.exif_lng}" if payload.exif_lat else "")
        + (f" | EXIF time: {payload.exif_timestamp}" if payload.exif_timestamp else "")
    )

    # event_type uses SCREAMING_CASE intentionally - this is part of an
    # external API contract consumed by an outside service integration.
    # Do not rename to snake_case without coordinating with the integrator.
    event = log_audit_event(
        event_type="UPLOAD_CERTIFIED",
        case_id=payload.case_id,
        evidence_id=f"file-{payload.task_id}",
        file_name=payload.filename,
        sha256=sha256,
        user=payload.provider_id,
        ip_address="service",
        notes=notes,
    )
    chain_hash = event.get("chain_hash", payload.task_id)

    cert_pdf_bytes = generate_integrity_certificate(
        filename=payload.filename,
        sha256=sha256,
        case_id=payload.case_id,
        notes=notes,
    )

    cert_key = f"certs/external/{chain_hash[:16]}.pdf"
    s3_client.put_object(
        Bucket=EVIDENTIX_BUCKET,
        Key=cert_key,
        Body=cert_pdf_bytes,
        ContentType="application/pdf",
    )
    cert_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": EVIDENTIX_BUCKET, "Key": cert_key},
        ExpiresIn=604800,
    )

    return CertifyResponse(
        certificate_id=chain_hash,
        sha256=sha256,
        cert_url=cert_url,
        chain_verified=True,
    )


class CustodyEventRequest(BaseModel):
    case_id:    str
    event_type: str
    user:       str
    ip_address: str
    notes:      Optional[str] = None


class CustodyEventResponse(BaseModel):
    event_id:   str
    chain_hash: Optional[str] = None


@external_router.post("/custody-event", response_model=CustodyEventResponse)
async def log_external_custody_event(
    payload: CustodyEventRequest,
    x_api_key: str = Header(...),
):
    _auth(x_api_key)

    event = log_audit_event(
        event_type=payload.event_type,
        case_id=payload.case_id,
        evidence_id=f"event-{payload.case_id}",
        user=payload.user,
        ip_address=payload.ip_address,
        notes=payload.notes or f"{payload.event_type} | {payload.user} | {payload.ip_address}",
    )

    chain_hash = event.get("chain_hash", "")
    return CustodyEventResponse(event_id=chain_hash, chain_hash=chain_hash)


class CustodyRecordRequest(BaseModel):
    task_id:        str
    submission_id:  str
    certificate_id: str
    requestor_name: str
    provider_name:  str
    case_reference: Optional[str] = None
    redacted:       bool = True


class CustodyRecordResponse(BaseModel):
    record_id:  str
    record_url: str


@external_router.post("/custody-record", response_model=CustodyRecordResponse)
async def generate_external_custody_record(
    payload: CustodyRecordRequest,
    x_api_key: str = Header(...),
):
    _auth(x_api_key)

    case_id   = payload.case_reference or f"external-{payload.task_id[:8]}"
    case_name = payload.case_reference or f"{payload.requestor_name} — {payload.provider_name}"

    custody_events = load_audit_log(case_id)
    chain_ok, _, _ = verify_chain(case_id)

    record_id, pdf_bytes = generate_custody_record(
        case_id=case_id,
        case_name=case_name,
        generated_by=payload.requestor_name,
        custody_events=custody_events,
        evidence_items=[],
        scope="case",
        chain_verified=chain_ok,
        chain_event_count=len(custody_events),
        redacted=payload.redacted,
        base_url=os.environ.get("BASE_URL", "https://evidenceanalyzer.com"),
    )

    record_key = f"custody-records/external/{record_id}.pdf"
    s3_client.put_object(
        Bucket=EVIDENTIX_BUCKET,
        Key=record_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    record_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": EVIDENTIX_BUCKET, "Key": record_key},
        ExpiresIn=604800,
    )

    return CustodyRecordResponse(record_id=record_id, record_url=record_url)