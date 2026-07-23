import json
import os
import shutil
import hashlib
import io
import tempfile
import zipfile
import secrets
import csv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import List, Optional

import requests
from sqlalchemy import Index, event, func
import stripe
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, Response
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from urllib.parse import quote
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app import db
from app.analyzer import analyze_file
from app.utils.audit_log import log_audit_event
from app.db import SessionLocal, engine
from app.models import Base, Case, Certificate, EvidenceItem, Payment, Subscription, User
from app.storage import upload_file, delete_object, delete_objects, get_file, generate_presigned_url
from app.email_alerts import send_upload_alert, send_chain_failure_alert, send_monthly_summary, send_verification_email
from app.auth import (
    require_verified_email,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_optional_user,
    get_db,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

from core.compare_files import compare_two_files, compare_against_case, compare_against_all_cases
from core.copyright_lookup import build_copyright_search_link


app = FastAPI()

@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    next_path = request.url.path
    if request.url.query:
        next_path += "?" + request.url.query
    if next_path and next_path != "/login":
        return RedirectResponse(url=f"/login?next={next_path}", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

# =========================================================
# PATHS / CONFIG
# =========================================================

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
CASES_DIR = PROJECT_ROOT / "cases"
REPORTS_DIR = PROJECT_ROOT / "reports"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

DATA_DIR.mkdir(exist_ok=True)
CASES_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# Schema is owned by Alembic in production. create_all runs ONLY when
# DB_CREATE_ALL is explicitly truthy (local/dev against a NON-prod DB), so that
# merely importing app.main can never create tables in prod. See CLAUDE.md.
if os.getenv("DB_CREATE_ALL", "").lower() in ("1", "true", "yes", "on"):
    Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Google Ads conversion tracking config - available to all templates
templates.env.globals["GOOGLE_ADS_ID"] = os.getenv("GOOGLE_ADS_ID", "")
templates.env.globals["GOOGLE_ADS_LABEL_PURCHASE"] = os.getenv("GOOGLE_ADS_LABEL_PURCHASE", "")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.mount("/case-files", StaticFiles(directory=str(CASES_DIR)), name="case-files")
app.mount("/report-files", StaticFiles(directory=str(REPORTS_DIR)), name="report-files")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
EVIDENTIX_DEV_MODE = os.getenv("EVIDENTIX_DEV_MODE") == "1"

def get_consent_state(request, current_user):
    """Resolve cookie consent state for a request.

    Returns "accepted", "declined", or "pending".

    Logged-in user with non-null cookie_consent in DB wins.
    Otherwise reads the cookie_consent cookie.
    If neither is set, honors the Sec-GPC: 1 header as a declined signal.
    "pending" means no decision recorded — show banner.
    """
    if current_user is not None and getattr(current_user, "cookie_consent", None) is not None:
        return "accepted" if current_user.cookie_consent else "declined"
    cookie_val = request.cookies.get("cookie_consent")
    if cookie_val == "accepted":
        return "accepted"
    if cookie_val == "declined":
        return "declined"
    # Honor Global Privacy Control browser signal as an automatic opt-out
    # per CCPA/CPRA enforcement guidance. User-explicit choices above
    # supersede this signal.
    if request.headers.get("sec-gpc") == "1":
        return "declined"
    return "pending"

# Privacy policy version - increment when the policy changes meaningfully
# so users re-consenting are recorded against the new version.
COOKIE_CONSENT_VERSION = "1"

SERVICE_MAP = {
    "single": {
        "name": "Single Image Analysis",
        "price": 250,
        "max_files": 1,
    },
    "comparison": {
        "name": "Comparison Report",
        "price": 500,
        "max_files": 10,
    },
    "investigation": {
        "name": "Evidentix Investigation",
        "price": 1500,
        "max_files": 25,
    },
}
TIER_LIMITS = {
    "monitoring_small":    25,
    "monitoring_standard": 100,
    "monitoring_large":    500,
}

def get_active_monitoring_sub(user_id: int, db: Session):
    """Return active monitoring subscription for a user, or None."""
    return db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.status == "active",
        Subscription.product.in_(["monitoring_small", "monitoring_standard", "monitoring_large"]),
    ).first()

# =========================================================
# HELPERS
# =========================================================

def load_cases_for_user(user: User):
    """Return cases belonging to this user (or all cases if admin)."""
    db = SessionLocal()
    try:
        query = db.query(Case).order_by(Case.id.asc())
        if not user.is_admin:
            query = query.filter(Case.user_id == user.id)
        cases = query.all()
        return [
            {
                "case_id": c.case_id,
                "case_name": c.case_name,
                "description": c.description or "",
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "",
            }
            for c in cases
        ]
    finally:
        db.close()




def create_case_folder(case_id: str):
    case_dir = CASES_DIR / case_id
    (case_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (case_dir / "reports").mkdir(parents=True, exist_ok=True)
    (case_dir / "comparisons").mkdir(parents=True, exist_ok=True)
    (case_dir / "audit").mkdir(parents=True, exist_ok=True)
    return case_dir


def safe_slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text.strip())
    return cleaned[:80] or "case"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_c2pa_analyzed_at(s):
    """Parse C2PA analyzed_at ISO string into a timezone-aware datetime.

    The upstream c2pa_analysis.summarize_for_certificate() returns analyzed_at
    as an ISO 8601 string with a 'Z' suffix. SQLAlchemy's DateTime(timezone=True)
    column expects a datetime object, so we parse here. Returns None on any
    failure so persistence never fails on a malformed timestamp.
    """
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def create_paid_case_id(service: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{service.upper()}-{ts}"


def verify_checkout_session(session_id: str):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe secret key not configured.")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unable to verify Stripe session: {e}")
    if getattr(session, "status", None) != "complete" or getattr(session, "payment_status", None) != "paid":
        raise HTTPException(status_code=403, detail="Stripe payment not completed.")
    return session


def assert_case_ownership(case_obj: Case, current_user: User):
    """Raise 403 if the user doesn't own the case (unless admin)."""
    if not current_user.is_admin and case_obj.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

# =========================================================
# AUTH ROUTES
# =========================================================

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    full_name: str = Form(...),
    firm_name: str = Form(""),
    country: str = Form(...),
    db: Session = Depends(get_db),
):
    import re

    error = None
    full_name_clean = full_name.strip()
    firm_name_clean = firm_name.strip()
    country_clean = country.strip().upper()

    if not full_name_clean:
        error = "Full name is required."
    elif not re.match(r"^[A-Z]{2}$", country_clean):
        error = "Please select a valid country."
    elif password != password_confirm:
        error = "Passwords do not match."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif db.query(User).filter(User.email == email.lower().strip()).first():
        error = "An account with that email already exists."

    if error:
        return templates.TemplateResponse(
            request, "register.html", {"error": error}, status_code=400
        )
    verification_token = secrets.token_urlsafe(48)
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    user = User(
        email=email.lower().strip(),
        hashed_password=hash_password(password),
        is_admin=False,
        full_name=full_name_clean,
        firm_name=firm_name_clean or None,
        country=country_clean,
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_token_expires=verification_expires,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        send_verification_email(user.email, verification_token)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to send verification email to {user.email}: {e}")

    token = create_access_token(user.id, user.email)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return resp

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: Optional[str] = None, verify_error: Optional[str] = None):
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": next, "verify_error": verify_error})

@app.get("/pricing")
async def pricing(request: Request):
    return templates.TemplateResponse(request, "pricing.html", {"pricing": PRICING})

@app.get("/sample")
async def sample():
    return RedirectResponse(url="https://evidentix-files-ken01.s3.us-west-2.amazonaws.com/Evidentix-Sample-Integrity-Certificate.pdf", status_code=303)


@app.get("/sample/comparison")
async def sample_comparison():
    return RedirectResponse(url="https://evidentix-files-ken01.s3.us-west-2.amazonaws.com/Evidentix-Sample-Comparison-Report.pdf", status_code=303)


@app.get("/compare-images", response_class=HTMLResponse)
async def compare_images_page(request: Request):
    return templates.TemplateResponse(request, "compare_images.html", {})


@app.get("/ai-sanctions")
async def ai_sanctions(request: Request):
    return templates.TemplateResponse(request, "ai_sanctions.html", {})

@app.get("/how-to-certify")
async def how_to_certify(request: Request):
    return templates.TemplateResponse(request, "how_to_certify.html", {"pricing": PRICING})

@app.get("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})

@app.get("/terms")
async def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})

@app.get("/dmca")
async def dmca(request: Request):
    return templates.TemplateResponse(request, "dmca.html", {})

@app.get("/cookie-preferences")
async def cookie_preferences(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    cookie_consent_state = get_consent_state(request, current_user)
    return templates.TemplateResponse(
        request,
        "cookie_preferences.html",
        {"current_user": current_user, "cookie_consent_state": cookie_consent_state},
    )


@app.get("/subpoena-policy")
async def subpoena_policy(request: Request):
    return templates.TemplateResponse(request, "subpoena_policy.html", {})

@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password.", "next": next},
            status_code=401,
        )

    token = create_access_token(user.id, user.email)
    redirect_to = next if next and next.startswith("/") and not next.startswith("//") else "/"
    resp = RedirectResponse(url="/dashboard?registered=1", status_code=303)
   
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("access_token")
    return resp


@app.get("/verify-email/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verification_token == token).first()

    if not user:
        return RedirectResponse(url="/login?verify_error=invalid", status_code=303)

    if user.email_verified:
        if user.email_verification_token:
            user.email_verification_token = None
            user.email_verification_token_expires = None
            db.commit()
        return RedirectResponse(url="/dashboard?verified=already", status_code=303)

    if user.email_verification_token_expires and user.email_verification_token_expires < datetime.now(timezone.utc):
        return RedirectResponse(url="/login?verify_error=expired", status_code=303)

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_token_expires = None
    db.commit()

    return RedirectResponse(url="/dashboard?verified=1", status_code=303)


@app.post("/resend-verification")
async def resend_verification(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.email_verified:
        return RedirectResponse(url="/dashboard?verified=already", status_code=303)

    # Rate limit: refuse if last token was issued less than 60 seconds ago.
    # Token expires 24h after issue, so issued_at = expires - 24h.
    if current_user.email_verification_token_expires:
        issued_at = current_user.email_verification_token_expires - timedelta(hours=24)
        seconds_since_last = (datetime.now(timezone.utc) - issued_at).total_seconds()
        if seconds_since_last < 60:
            wait = int(60 - seconds_since_last)
            return RedirectResponse(url=f"/dashboard?resend_cooldown={wait}", status_code=303)

    verification_token = secrets.token_urlsafe(48)
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    current_user.email_verification_token = verification_token
    current_user.email_verification_token_expires = verification_expires
    db.commit()

    try:
        send_verification_email(current_user.email, verification_token)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to resend verification email to {current_user.email}: {e}")

    return RedirectResponse(url="/dashboard?resent=1", status_code=303)


# =========================================================
# PUBLIC PAGES
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "compare_images.html", {})


# =========================================================
# BASIC CASE WORKFLOW  (all routes now require login)
# =========================================================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    cookie_consent_state = get_consent_state(request, current_user)
    cases = load_cases_for_user(current_user)
    deleted = request.query_params.get("deleted")
    verified = request.query_params.get("verified")

    message = None
    if deleted:
        message = "Case deleted successfully."
    elif verified == "1":
        message = "Email verified successfully. Welcome to Evidentix."
    elif verified == "already":
        message = "Your email is already verified."
    elif request.query_params.get("resent") == "1":
        message = "Verification email resent. Please check your inbox."
    elif request.query_params.get("resend_cooldown"):
        wait = request.query_params.get("resend_cooldown")
        message = f"Please wait {wait} seconds before requesting another verification email."

    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "cases": cases,
            "current_user": current_user,
            "message": message,
            "pricing": PRICING,
        },
    )

@app.post("/create-case", response_class=HTMLResponse)
async def create_case(
    request: Request,
    case_name: str = Form(...),
    description: str = Form(""),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    new_case = Case(
        case_id="",  # placeholder; assigned after flush
        case_name=case_name,
        description=description,
        user_id=current_user.id,
    )
    db.add(new_case)
    db.flush()  # assigns new_case.id without committing
    case_id = f"CASE-{new_case.id:04d}"
    new_case.case_id = case_id
    db.commit()

    create_case_folder(case_id)

    updated_data = load_cases_for_user(current_user)

    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "cases": updated_data,
            "current_user": current_user,
            "message": f"Case created successfully: {case_id}",
            "pricing": PRICING,
        },
    )


@app.post("/delete-case/{case_id}")

async def delete_case(
    case_id: str,
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()

    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")

    assert_case_ownership(case_obj, current_user)

    # Gather S3 keys BEFORE deleting DB rows
    evidence_keys = [e.file_key for e in db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()]
    certificate_keys = [c.pdf_key for c in db.query(Certificate).filter(Certificate.case_id == case_id).all()]
    all_s3_keys = evidence_keys + certificate_keys

    log_audit_event(
        event_type="case_deleted",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Case and all evidence deleted by authenticated user",
    )

    from app.models import FingerprintIndex
    db.query(FingerprintIndex).filter(FingerprintIndex.case_id == case_id).delete()
    db.query(Certificate).filter(Certificate.case_id == case_id).delete()
    db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).delete()
    db.delete(case_obj)
    db.commit()

    # Delete S3 objects (idempotent; failures swallowed in storage helper)
    delete_objects(all_s3_keys)

    case_dir = CASES_DIR / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)

    return RedirectResponse(url="/dashboard?deleted=1", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Case).order_by(Case.id.asc())
    if not current_user.is_admin:
        query = query.filter(Case.user_id == current_user.id)
    cases = query.all()

    items = []
    for case in cases:
        file_count = (
            db.query(EvidenceItem)
            .filter(EvidenceItem.case_id == case.case_id)
            .count()
        )
        items.append(
            {
                "case_id": case.case_id,
                "case_name": case.case_name,
                "description": case.description or "",
                "created_at": case.created_at.strftime("%Y-%m-%d %H:%M:%S") if case.created_at else "",
                "file_count": file_count,
            }
        )

    return templates.TemplateResponse(
        request,
        "reports.html",
        {"items": items, "current_user": current_user},
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail(
    request: Request,
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploaded = request.query_params.get("uploaded")

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()

    if not case_obj:
        return HTMLResponse(f"<h1>Case {case_id} not found</h1>", status_code=404)

    assert_case_ownership(case_obj, current_user)

    log_audit_event(
        event_type="file_viewed",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Case detail page viewed",
    )

    case_record = {

        "case_id": case_obj.case_id,
        "case_name": case_obj.case_name,
        "description": case_obj.description or "",
        "created_at": case_obj.created_at.strftime("%Y-%m-%d %H:%M:%S") if case_obj.created_at else "",
    }

    evidence_rows = (
        db.query(EvidenceItem)
        .filter(EvidenceItem.case_id == case_id)
        .order_by(EvidenceItem.id.asc())
        .all()
    )

    evidence_items = [
        {
            "evidence_id": e.evidence_id,
            "file_name": e.file_name,
            "sha256": e.sha256,
            "phash": e.phash,
            "analysis_date": e.analysis_date,
            "json_report": e.json_report,
            "pdf_report": e.pdf_report,
            "file_key": e.file_key,
        }
        for e in evidence_rows
    ]

    return templates.TemplateResponse(
        request,
        "case_detail.html",
        {
            "case": case_record,
            "evidence_items": evidence_items,
            "uploaded": uploaded,
            "current_user": current_user,
        },
    )


@app.post("/analyze")
async def analyze_file_route(
    request: Request,
    case_id: str = Form(...),
    file: UploadFile = File(...),
    web_detection_enabled: bool = Form(False),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    # Monitoring tier — file count enforcement (before any work happens)
    sub = get_active_monitoring_sub(current_user.id, db)
    if sub:
        tier_limit = TIER_LIMITS.get(sub.product, 25)
        current_count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).count()
        if current_count >= tier_limit:
            raise HTTPException(
                status_code=403,
                detail=f"File limit reached for your monitoring tier ({tier_limit} files). Upgrade to add more files.",
            )

    case_dir = CASES_DIR / case_id
    case_upload_dir = case_dir / "uploads"
    case_upload_dir.mkdir(parents=True, exist_ok=True)

    import uuid
    evidence_id = str(uuid.uuid4())

    file_path = case_upload_dir / file.filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file.file.seek(0)

    file_key = upload_file(file.file, file.filename, file.content_type)
    log_audit_event(
        event_type="file_uploaded",
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file.filename,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Evidence file uploaded",
    )

    report, json_path, pdf_path = analyze_file(
        str(file_path),
        case_dir=str(case_dir),
        file_key=file_key,
        web_detection_enabled=web_detection_enabled,
    )
    c2pa_data = report.get("c2pa", {}) or {}
    new_item = EvidenceItem(
        evidence_id=evidence_id,
        case_id=case_id,
        file_name=file.filename,
        file_key=file_key,
        json_report=json_path,
        sha256=report.get("sha256"),
        analysis_date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        web_detection_enabled=web_detection_enabled,
        # C2PA Content Credentials (from c2pa_analysis.summarize_for_certificate)
        c2pa_state=c2pa_data.get("state"),
        c2pa_has_ai_generation=c2pa_data.get("has_ai_generation"),
        c2pa_has_ai_modification=c2pa_data.get("has_ai_modification"),
        c2pa_signature_valid=c2pa_data.get("signature_valid"),
        c2pa_claim_generator=c2pa_data.get("claim_generator"),
        c2pa_signature_issuer=c2pa_data.get("signature_issuer"),
        c2pa_signature_time=c2pa_data.get("signature_time"),
        c2pa_plain_english=c2pa_data.get("plain_english"),
        c2pa_analyzed_at=_parse_c2pa_analyzed_at(c2pa_data.get("analyzed_at")),
        c2pa_claim_generator_version=c2pa_data.get("claim_generator_version"),
        c2pa_num_assertions=c2pa_data.get("num_assertions"),
        c2pa_num_ingredients=c2pa_data.get("num_ingredients"),
        c2pa_trust_list_status=c2pa_data.get("trust_list_status"),
        c2pa_revocation_status=c2pa_data.get("revocation_status"),
        c2pa_ai_agents_found=c2pa_data.get("ai_agents_found"),
        c2pa_has_training_mining=c2pa_data.get("has_training_mining"),
    )

    log_audit_event(
        event_type="analysis_completed",
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file.filename,
        sha256=report.get("sha256"),
        user=current_user.email,
        ip_address=request.client.host,
        notes="Image analysis and forensic report generated",
        extra={
            "json_report": json_path,
            "pdf_report": pdf_path,
            "s3_file_key": file_key,
        },
    )

    # Save EvidenceItem to DB

    db.add(new_item)
    db.commit()
# Add to fingerprint index for comparison searches
    from core.fingerprint_index import add_fingerprint
    add_fingerprint(
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file.filename,
        phash=report.get("phash"),
        json_report=json_path,
    )

    # Monitoring — upload alert (tier already validated at start of route)
    if sub:
        base_url = str(request.base_url).rstrip("/")
        send_upload_alert(
            to_email=current_user.email,
            case_id=case_id,
            case_name=case_obj.case_name,
            file_name=file.filename,
            evidence_id=evidence_id,
            sha256=report.get("sha256", "—"),
            uploaded_by=current_user.email,
            base_url=base_url,
        )

    return RedirectResponse(url=f"/cases/{case_id}?uploaded=1", status_code=303)

@app.get("/evidence-file/{case_id}/{evidence_id}")
async def evidence_file_redirect(
    case_id: str,
    evidence_id: str,
    request: Request, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )

    if not item or not item.file_key:
        raise HTTPException(status_code=404, detail="Original file not found.")

    # Verify ownership via the case
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    log_audit_event(
        event_type="file_accessed",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Original evidence file accessed: {item.file_name}",
    )

    url = generate_presigned_url(item.file_key)
    return RedirectResponse(url=url, status_code=302)

# =========================================================
# COMPARISON WORKFLOW  (login required)
# =========================================================

@app.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "compare.html", {"current_user": current_user})


@app.post("/compare", response_class=HTMLResponse)
async def compare_submit(
    request: Request,
    case_name: str = Form(...),
    client_name: str = Form(""),
    case_notes: str = Form(""),
    original_file: UploadFile = File(...),
    suspected_file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    # Comparison credit gate: 402 into checkout when no unconsumed credit.
    from app.entitlements import assert_compare_entitlement, consume_compare_credit
    try:
        _compare_credit = assert_compare_entitlement(db, current_user)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(url="/checkout/comparison", status_code=303)
        raise
    safe_case_name = safe_slug(case_name)
    case_path = REPORTS_DIR / safe_case_name
    case_path.mkdir(parents=True, exist_ok=True)

    original_path = case_path / original_file.filename
    suspected_path = case_path / suspected_file.filename

    with original_path.open("wb") as f:
        shutil.copyfileobj(original_file.file, f)

    with suspected_path.open("wb") as f:
        shutil.copyfileobj(suspected_file.file, f)
    comparison_data = compare_two_files(str(original_path), str(suspected_path), str(case_path))
    consume_compare_credit(db, _compare_credit)
    comparison = {
        "case_id": None,
        "suspect_file": suspected_file.filename,
        "best_match": comparison_data,
        "matches": [comparison_data],
    }

    log_audit_event(
        event_type="comparison_performed",
        case_id="COMPARE",
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Two-file comparison performed: {original_file.filename} vs {suspected_file.filename}",
    )

    return templates.TemplateResponse(
        request,
        "compare_result.html",
        {
            "result": comparison,
            "case_name": case_name,
            "client_name": client_name,
            "case_notes": case_notes,
            "current_user": current_user,
        },
    )
@app.get("/compare-against-case", response_class=HTMLResponse)
async def compare_against_case_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cases = load_cases_for_user(current_user)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {"current_user": current_user, "cases": cases},
    )

@app.post("/compare-against-case", response_class=HTMLResponse)
async def compare_against_case_route(
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    form = await request.form()
    raw_case_id = form.get("case_id")
    file = form.get("file")

    case_id = str(raw_case_id).strip() if raw_case_id else ""

    if not case_id or not file or not getattr(file, "filename", ""):
        return templates.TemplateResponse(
            request,
            "compare_result.html",
            {
                "error": f"Missing case_id or file.",
                "result": None,
                "current_user": current_user,
            },
            status_code=400,
        )

    # Comparison credit gate: 402 into checkout when no unconsumed credit.
    from app.entitlements import assert_compare_entitlement, consume_compare_credit
    try:
        _compare_credit = assert_compare_entitlement(db, current_user)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(url="/checkout/comparison", status_code=303)
        raise
    # Ownership check
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    upload_dir = PROJECT_ROOT / "temp_uploads"
    upload_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / safe_filename

    with file_path.open("wb") as f:
        f.write(await file.read())

    try:
        result = compare_against_case(str(file_path), case_id)
        consume_compare_credit(db, _compare_credit)
        log_audit_event(
            event_type="comparison_performed",
            case_id=case_id,
            user=current_user.email,
            ip_address=request.client.host,
            notes=f"File compared against case {case_id}",
        )

        return templates.TemplateResponse(
            request,
            "compare_result.html",
            {"error": None, "result": result, "current_user": current_user},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "compare_result.html",
            {"error": str(e), "result": None, "current_user": current_user},
            status_code=500,
        )


@app.post("/compare-case", response_class=HTMLResponse)
async def compare_case_route(
    request: Request,
    case_id: str = Form(...),
    suspect_file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    # Comparison credit gate: 402 into checkout when no unconsumed credit.
    from app.entitlements import assert_compare_entitlement, consume_compare_credit
    try:
        _compare_credit = assert_compare_entitlement(db, current_user)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(url="/checkout/comparison", status_code=303)
        raise
    compare_dir = CASES_DIR / case_id / "comparisons"
    compare_dir.mkdir(parents=True, exist_ok=True)

    suspect_path = compare_dir / suspect_file.filename

    with suspect_path.open("wb") as buffer:
        buffer.write(await suspect_file.read())

    result = compare_against_case(str(suspect_path), case_id=case_id)
    consume_compare_credit(db, _compare_credit)

    log_audit_event(
            event_type="case_comparison_completed",
            case_id=case_id,
            file_name=suspect_file.filename,
            user=current_user.email,
            ip_address=request.client.host,
            notes="Suspect image compared against evidence in selected case",
            extra={
                "best_match_file": result.get("best_match", {}).get("original_file") if result.get("best_match") else None,
                "similarity_score": result.get("best_match", {}).get("similarity_score") if result.get("best_match") else None,
                "match_count": len(result.get("matches", [])),
            },
        )
    return templates.TemplateResponse(
            request,
            "compare_case_result.html",
            {
                "case_id": case_id,
                "suspect_file": suspect_file.filename,
                "suspect_phash": result.get("suspect_phash"),
                "comparison": {
                **(result.get("best_match") or {}),
                "conclusion": (result.get("best_match") or {}).get("conclusion_text", ""),
            },
                "clip_score_pct": (result.get("best_match") or {}).get("clip_score_pct", "N/A"),
                "matches": result.get("matches", []),
                "current_user": current_user,
            },
        )

@app.post("/compare-global", response_class=HTMLResponse)
async def compare_global_route(
    request: Request,
    suspect_file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    # Comparison credit gate: 402 into checkout when no unconsumed credit.
    from app.entitlements import assert_compare_entitlement, consume_compare_credit
    try:
        _compare_credit = assert_compare_entitlement(db, current_user)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(url="/checkout/comparison", status_code=303)
        raise
    temp_dir = UPLOADS_DIR / "temp_compare"
    temp_dir.mkdir(parents=True, exist_ok=True)

    suspect_path = temp_dir / suspect_file.filename

    with suspect_path.open("wb") as buffer:
        buffer.write(await suspect_file.read())
    from app.db import SessionLocal
    from app.models import EvidenceItem as _EI
    _db = SessionLocal()
    _ids = [r[0] for r in _db.query(_EI.case_id).distinct().all()]
    _db.close()
    print(f"DEBUG direct query case_ids: {_ids}", flush=True)

    result = compare_against_all_cases(str(suspect_path), cases_root=str(CASES_DIR))
    consume_compare_credit(db, _compare_credit)
    log_audit_event(
        event_type="global_comparison_completed",
        case_id="GLOBAL",
        file_name=suspect_file.filename,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Image compared against all cases",
        extra={"match_count": len(result.get("matches", []))},
    )
    return templates.TemplateResponse(
            request,
            "compare_global_result.html",
            {
                "result": result,          # ADD THIS LINE
                "suspect_file": suspect_file.filename,
                "suspect_phash": result.get("suspect_phash"),
                "matches": result.get("matches", []),
                "current_user": current_user,
            },
        )

# =========================================================
# BATCH SCAN  (login required)
# =========================================================

# =========================================================
# COPYRIGHT SEARCH  (login required)
# =========================================================

@app.get("/copyright-search", response_class=HTMLResponse)
async def copyright_search_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "copyright_search.html",
        {
            "search_link": None,
            "title": "",
            "author": "",
            "claimant": "",
            "registration_number": "",
            "year": "",
            "current_user": current_user,
        },
    )


@app.post("/copyright-search", response_class=HTMLResponse)
async def copyright_search_submit(
    request: Request,
    title: str = Form(""),
    author: str = Form(""),
    claimant: str = Form(""),
    registration_number: str = Form(""),
    year: str = Form(""),
    current_user: User = Depends(require_verified_email),
):
    search_link = build_copyright_search_link(
        title=title,
        author=author,
        claimant=claimant,
        registration_number=registration_number,
        year=year,
    )

    return templates.TemplateResponse(
        request,
        "copyright_search.html",
        {
            "search_link": search_link,
            "title": title,
            "author": author,
            "claimant": claimant,
            "registration_number": registration_number,
            "year": year,
            "current_user": current_user,
        },
    )
# =========================================================
# ADMIN ROUTES
# =========================================================

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    users = db.query(User).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "current_user": current_user,
            "users": users,
        },
    )


# ── Channel-billing pilot: read-only per-partner Integrity Certificate usage ──
# Partner accounts are hardcoded for the pilot (promote to a users.is_partner
# column later). Matched case-insensitively against Certificate.generated_by.
PARTNER_EMAILS = {
    "intake@evidenceanalyzer.com",
}
_USAGE_TZ = ZoneInfo("America/Chicago")
_USAGE_TZ_LABEL = "America/Chicago"


def _usage_csv(header, rows, filename):
    """Build an attachment CSV Response from a header row and list-of-rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/usage")
async def admin_usage(
    request: Request,
    month: str,
    account_id: Optional[str] = None,
    fmt: str = "html",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    # Parse YYYY-MM into a half-open [start, end) window in the business timezone.
    try:
        year, mon = (int(p) for p in month.split("-"))
        start = datetime(year, mon, 1, tzinfo=_USAGE_TZ)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format.")
    end = datetime(year + (mon // 12), (mon % 12) + 1, 1, tzinfo=_USAGE_TZ)

    # Exclude admin/internal accounts (matched case-insensitively on email).
    admin_emails = [
        e.lower()
        for (e,) in db.query(User.email).filter(User.is_admin == True).all()
        if e
    ]

    # Base filter: successful Integrity Certificate generations in the window.
    # A certificates row is written only after successful generation + S3 upload
    # + commit, so row existence == success; re-downloads create no new row.
    base = db.query(Certificate).filter(
        Certificate.type == "integrity",
        Certificate.created_at >= start,
        Certificate.created_at < end,
    )
    if admin_emails:
        base = base.filter(func.lower(Certificate.generated_by).notin_(admin_emails))

    # Drill-down: one row per certificate for the named account.
    if account_id:
        rows = (
            base.filter(func.lower(Certificate.generated_by) == account_id.lower())
            .order_by(Certificate.created_at.asc())
            .all()
        )
        records = [
            {
                "certificate_id": c.certificate_id,
                "case_id": c.case_id,
                "created_at": (
                    c.created_at.astimezone(_USAGE_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    if c.created_at else ""
                ),
            }
            for c in rows
        ]
        if fmt == "csv":
            return _usage_csv(
                ["certificate_id", "case_id", f"created_at ({_USAGE_TZ_LABEL})"],
                [[r["certificate_id"], r["case_id"], r["created_at"]] for r in records],
                f"usage_{month}_{account_id}.csv",
            )
        return templates.TemplateResponse(
            request,
            "admin_usage.html",
            {
                "current_user": current_user,
                "month": month,
                "tz_label": _USAGE_TZ_LABEL,
                "account_id": account_id,
                "records": records,
                "summary": None,
            },
        )

    # Summary: billable Integrity Certificate count per partner account.
    # With no partners configured, show a notice rather than every account.
    partners_configured = bool(PARTNER_EMAILS)
    summary = []
    if partners_configured:
        summary_q = (
            base.with_entities(
                Certificate.generated_by.label("account"),
                func.count(func.distinct(Certificate.certificate_id)).label("billable_certs"),
            )
            .filter(func.lower(Certificate.generated_by).in_(PARTNER_EMAILS))
            .group_by(Certificate.generated_by)
        )
        summary = [
            {"account": account, "billable_certs": n}
            for (account, n) in summary_q.all()
        ]

    if fmt == "csv":
        return _usage_csv(
            ["account_email", "billable_certs"],
            [[s["account"], s["billable_certs"]] for s in summary],
            f"usage_{month}.csv",
        )
    return templates.TemplateResponse(
        request,
        "admin_usage.html",
        {
            "current_user": current_user,
            "month": month,
            "tz_label": _USAGE_TZ_LABEL,
            "account_id": None,
            "records": None,
            "summary": summary,
            "partners_configured": partners_configured,
        },
    )


# ── Free image screen: authenticated, images-only, ephemeral, quota-limited ──
# Reuses the verification primitives DIRECTLY (sha256_file, c2pa_analysis,
# extract_exif) — never the cert/PDF path. Persists ONLY a FreeScreenLog audit
# row (c2pa_state + sha256); no EvidenceItem, no S3 object, no FingerprintIndex
# write, no custody-log event, no PDF. search_similar is intentionally NOT
# called (it reads the shared cross-customer index). The SHOW/WITHHOLD contract
# is enforced by the response dict below: present/missing metadata only (no EXIF
# dump, no GPS, no map), C2PA ingredients only for the derivative signal.
FREE_SCREEN_MONTHLY_QUOTA = 10
_FREE_SCREEN_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
_FREE_SCREEN_DISCLAIMER = (
    "Informational screen — not the Integrity Certificate, not exhibit-ready."
)


def _free_screen_quota(db, user_id):
    """Current free-screen usage for an account in this calendar month, counted
    in the business timezone — same window POST /screen enforces. Returns
    (used, limit, resets_iso_date). Read-only; a future cleanup could have
    POST /screen call this too (kept separate for now to avoid endpoint churn).
    """
    from app.models import FreeScreenLog

    now = datetime.now(_USAGE_TZ)
    start = datetime(now.year, now.month, 1, tzinfo=_USAGE_TZ)
    end = datetime(now.year + (now.month // 12), (now.month % 12) + 1, 1, tzinfo=_USAGE_TZ)
    used = (
        db.query(FreeScreenLog)
        .filter(
            FreeScreenLog.user_id == user_id,
            FreeScreenLog.created_at >= start,
            FreeScreenLog.created_at < end,
        )
        .count()
    )
    return used, FREE_SCREEN_MONTHLY_QUOTA, end.date().isoformat()


@app.get("/screen", response_class=HTMLResponse)
async def screen_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Page is verified-gated at the UI level: only verified users see a working
    # uploader; unverified users get a friendly prompt and NO submittable
    # dropzone. The actual screen is enforced server-side by POST /screen
    # (require_verified_email), so the gate cannot be bypassed from the client.
    used, limit, resets = _free_screen_quota(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "screen.html",
        {
            "current_user": current_user,
            "used": used,
            "limit": limit,
            "resets": resets,
        },
    )


@app.post("/screen")
async def free_screen(
    file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from app.models import FreeScreenLog
    from app.utils.hash_utils import sha256_file
    from app.utils.metadata_utils import extract_exif
    from app.c2pa_analysis import (
        analyze_file as c2pa_analyze_file,
        summarize_for_certificate,
    )

    # Images only — rejects PDF, video, and anything else.
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _FREE_SCREEN_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail="The free screen accepts image files only (jpg, jpeg, png, webp).",
        )

    # Per-account monthly quota, counted in the business-timezone month window.
    now = datetime.now(_USAGE_TZ)
    start = datetime(now.year, now.month, 1, tzinfo=_USAGE_TZ)
    end = datetime(now.year + (now.month // 12), (now.month % 12) + 1, 1, tzinfo=_USAGE_TZ)
    resets = end.date().isoformat()
    used_before = (
        db.query(FreeScreenLog)
        .filter(
            FreeScreenLog.user_id == current_user.id,
            FreeScreenLog.created_at >= start,
            FreeScreenLog.created_at < end,
        )
        .count()
    )
    if used_before >= FREE_SCREEN_MONTHLY_QUOTA:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly free-screen limit ({FREE_SCREEN_MONTHLY_QUOTA}) reached. "
                f"Resets {resets}."
            ),
        )

    # Ephemeral temp file, deleted in finally. Nothing is uploaded or retained.
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        sha256 = sha256_file(tmp_path)
        result = c2pa_analyze_file(tmp_path)
        c2pa_summary = summarize_for_certificate(result)
        exif = extract_exif(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Metadata: present/missing only (mirrors analyzer.metadata_status). No EXIF
    # field dump, no GPS coordinates, no map — those are the paid certificate.
    exif_present = bool(exif) and "error" not in exif and exif != {}

    # Derivative signal: C2PA-declared parent files only (title, relationship,
    # has_manifest). NOT search_similar / perceptual-hash cross-file matching.
    ingredients = [
        {
            "title": ing.get("title"),
            "relationship": ing.get("relationship"),
            "has_manifest": ing.get("has_manifest"),
        }
        for ing in result.ingredients
    ]

    # Persist the minimal audit row only — state + hash, no filename/media.
    db.add(FreeScreenLog(
        user_id=current_user.id,
        c2pa_state=c2pa_summary["state"],
        sha256=sha256,
    ))
    db.commit()

    return {
        "sha256": sha256,
        "c2pa": {
            "state": c2pa_summary["state"],
            "label": c2pa_summary["state_label"],
            "ai_flags": {
                "generation": c2pa_summary["has_ai_generation"],
                "modification": c2pa_summary["has_ai_modification"],
                "training_mining": c2pa_summary["has_training_mining"],
            },
        },
        "metadata": {
            "status": "present" if exif_present else "missing",
            "exif_present": exif_present,
        },
        "derivative": {
            "flag": bool(ingredients),
            "ingredients": ingredients,
        },
        "quota": {
            "used": used_before + 1,
            "limit": FREE_SCREEN_MONTHLY_QUOTA,
            "resets": resets,
        },
        "disclaimer": _FREE_SCREEN_DISCLAIMER,
    }


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    from app.models import Subscription

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    event_id = event["id"]
    data_object = event["data"]["object"].to_dict()

    # Idempotency guard — skip if we've already processed this event
    existing = db.query(Payment).filter(Payment.stripe_event_id == event_id).first()
    if existing:
        return {"status": "already_processed"}

    if event_type == "checkout.session.completed":
        customer_details = data_object.get("customer_details") or {}
        metadata = data_object.get("metadata") or {}

        _meta_user_id = metadata.get("user_id")
        # /success owns the integrity-cert insert (race-safe path). If a row
        # already exists for this session, skip -- do not double-insert
        # (stripe_session_id is unique). Other products still insert here.
        _existing = db.query(Payment).filter(
            Payment.stripe_session_id == data_object["id"]
        ).first()
        if _existing is None:
            payment = Payment(
                stripe_session_id=data_object["id"],
                stripe_event_id=event_id,
                stripe_customer_email=customer_details.get("email"),
                stripe_amount_total=data_object.get("amount_total"),
                stripe_currency=data_object.get("currency"),
                product=metadata.get("product"),
                status="paid",
                user_id=int(_meta_user_id) if _meta_user_id else None,
                case_id=metadata.get("case_id") or None,
                evidence_id=metadata.get("evidence_id") or None,
            )
            db.add(payment)
            db.commit()

    elif event_type == "invoice.paid":
        subscription_id = data_object.get("subscription")
        customer_id = data_object.get("customer")
        customer_email = data_object.get("customer_email")

        if subscription_id:
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()

            if sub:
                sub.status = "active"
                sub.updated_at = datetime.now(timezone.utc)
                db.commit()
            else:
                # First invoice.paid for this subscription — create the record
                stripe_sub = stripe.Subscription.retrieve(subscription_id).to_dict()
                product_id = stripe_sub["items"]["data"][0]["price"]["id"] if stripe_sub["items"]["data"] else None

                new_sub = Subscription(
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    stripe_customer_email=customer_email,
                    product=product_id,
                    status="active",
                )
                db.add(new_sub)
                db.commit()

    elif event_type == "customer.subscription.updated":
        subscription_id = data_object.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()

        if sub:
            sub.status = data_object.get("status", sub.status)
            sub.updated_at = datetime.now(timezone.utc)
            db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription_id = data_object.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()

        if sub:
            sub.status = "canceled"
            sub.updated_at = datetime.now(timezone.utc)
            db.commit()

    elif event_type == "invoice.payment_failed":
        subscription_id = data_object.get("subscription")
        if subscription_id:
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()

            if sub:
                sub.status = "past_due"
                sub.updated_at = datetime.now(timezone.utc)
                db.commit()

    return {"status": "ok"}

# =========================================================
# STRIPE CHECKOUT ROUTES
# =========================================================
STRIPE_PRICES = {
    # Active SKUs
    "video_single": "price_1TIqApHVHQNKUlwksbqqdsqA",
    "bundle": "price_1THUiNHVHQNKUlwkJG0v91C7",
    "video_image_bundle": "price_1TIqE7HVHQNKUlwk8v4FmJnP",
    "video_bundle": "price_1TIqCcHVHQNKUlwk6tJXz5Uo",
    # RETIRED 2026-05-25: Professional Plan pulled per SKU lock; product had no code-level gating; Stripe price deactivated.
    # "professional": "price_1THV2DHVHQNKUlwkZ5lyCBsE",
    # RETIRED 2026-05-25: Firm License SKU pulled per pricing rationalization; Stripe price deactivated.
    # "firm": "price_1THV6cHVHQNKUlwkViPyHk4f",

    # New Phase 2 SKUs — replace placeholder values with real Stripe price IDs
    # after creating them in the Stripe dashboard
    "integrity_certificate": "price_1TcliWHVHQNKUlwkmGokLuMI",
    "custody_record": "price_1TPmDkHVHQNKUlwkj0AweJ9g",
    "monitoring_small": "price_1TPmFhHVHQNKUlwkRHoGFIyF",
    "monitoring_standard": "price_1TPmGvHVHQNKUlwkfr5LTk9G",
    "monitoring_large": "price_1TPmISHVHQNKUlwkcyt08yd4",
    "comparison": "price_1Tw2vpHVHQNKUlwkwr2DzdaQ",
}
PRICING = {
    "integrity_certificate": {"name": "Integrity Certificate",   "price": "$99",       "per": "per file"},
    "custody_record":        {"name": "Custody Record",          "price": "$199",      "per": "per case"},
    "comparison":            {"name": "Comparison Report",       "price": "$149",      "per": "per comparison"},
    "video_single":          {"name": "Single Video Analysis",   "price": "$199",      "per": "per video"},
    "bundle":                {"name": "Case Bundle",             "price": "$299",      "per": "up to 10 images"},
    "video_image_bundle":    {"name": "Video + Image Bundle",    "price": "$399",      "per": "per case"},
    "video_bundle":          {"name": "Video Bundle",            "price": "$599",      "per": "up to 5 videos"},
    "monitoring_small":      {"name": "Monitoring — Small",      "price": "$49/mo",    "per": "up to 25 files"},
    "monitoring_standard":   {"name": "Monitoring — Standard",   "price": "$99/mo",   "per": "up to 100 files"},
    "monitoring_large":      {"name": "Monitoring — Large",      "price": "$199/mo",   "per": "up to 500 files"},
    # RETIRED 2026-05-25: Professional Plan pulled per SKU lock; product had no code-level gating; Stripe price deactivated.
    # "professional":          {"name": "Professional Plan",       "price": "$399/mo",   "per": "up to 150 analyses"},
    # RETIRED 2026-05-25: Firm License SKU pulled per pricing rationalization; Stripe price deactivated.
    # "firm":                  {"name": "Firm License",            "price": "$7,500/yr", "per": "unlimited"},
}

# Subscription products — used to determine checkout mode
SUBSCRIPTION_PRODUCTS = {
    "monitoring_small", "monitoring_standard", "monitoring_large"  # "firm" RETIRED 2026-05-25; "professional" RETIRED 2026-05-25
}

STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")


@app.get("/checkout/{product}", response_class=HTMLResponse)
async def checkout(
    request: Request,
    product: str,
    case_id: str = "",
    evidence_id: str = "",
    current_user: User = Depends(require_verified_email),
):
    if product not in STRIPE_PRICES:
        raise HTTPException(status_code=404, detail="Product not found.")

    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured.")

    base_url = str(request.base_url).rstrip("/")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price": STRIPE_PRICES[product],
                "quantity": 1,
            }
        ],
        mode="subscription" if product in SUBSCRIPTION_PRODUCTS else "payment",
        success_url=(
            f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}&product={product}"
            + (f"&case_id={quote(case_id)}&evidence_id={quote(evidence_id)}"
               if case_id and evidence_id else "")
        ),
        cancel_url=f"{base_url}/cancel",
        customer_email=current_user.email,
        allow_promotion_codes=True,
        metadata={
            "product": product,
            "user_id": str(current_user.id),
            "case_id": case_id,
            "evidence_id": evidence_id,
        },
    )

    return RedirectResponse(url=session.url, status_code=303)


@app.get("/success", response_class=HTMLResponse)
async def checkout_success(
    request: Request,
    session_id: str = "",
    product: str = "",
    case_id: str = "",
    evidence_id: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if session_id and product == "integrity_certificate":
        # Path 2 / Option B, race-safe: confirm payment with Stripe directly
        # (immune to webhook timing), ensure the Payment row exists, THEN
        # redirect into generate. File ids come from the VERIFIED session
        # metadata, not the query string (which a user could tamper with).
        try:
            session = verify_checkout_session(session_id)
        except HTTPException:
            return RedirectResponse(
                url="/checkout/integrity_certificate"
                    + (f"?case_id={quote(case_id)}&evidence_id={quote(evidence_id)}"
                       if case_id and evidence_id else ""),
                status_code=303,
            )
        session = session.to_dict()
        meta = dict(session.get("metadata") or {})
        m_user_id = meta.get("user_id")
        m_case_id = meta.get("case_id") or ""
        m_evidence_id = meta.get("evidence_id") or ""
        # Idempotent: /success owns the insert; create only if absent.
        existing = db.query(Payment).filter(
            Payment.stripe_session_id == session_id
        ).first()
        if existing is None:
            db.add(Payment(
                stripe_session_id=session_id,
                stripe_customer_email=(session.get("customer_details") or {}).get("email"),
                stripe_amount_total=session.get("amount_total"),
                stripe_currency=session.get("currency"),
                product=meta.get("product"),
                status="paid",
                user_id=int(m_user_id) if m_user_id else None,
                case_id=m_case_id or None,
                evidence_id=m_evidence_id or None,
            ))
            db.commit()
        if m_case_id and m_evidence_id:
            return RedirectResponse(
                url=f"/generate/integrity/{quote(m_case_id)}/{quote(m_evidence_id)}",
                status_code=303,
            )
    if session_id and product == "comparison":
        # Race-safe: confirm payment with Stripe directly and ensure the
        # Payment row (comparison credit) exists before the user returns to
        # /compare, immune to webhook timing. Idempotent like the cert path.
        try:
            _s = verify_checkout_session(session_id)
        except HTTPException:
            _s = None
        if _s is not None:
            _s = _s.to_dict()
            _meta = dict(_s.get("metadata") or {})
            _uid = _meta.get("user_id")
            _existing = db.query(Payment).filter(
                Payment.stripe_session_id == session_id
            ).first()
            if _existing is None:
                db.add(Payment(
                    stripe_session_id=session_id,
                    stripe_customer_email=(_s.get("customer_details") or {}).get("email"),
                    stripe_amount_total=_s.get("amount_total"),
                    stripe_currency=_s.get("currency"),
                    product=_meta.get("product"),
                    status="paid",
                    user_id=int(_uid) if _uid else None,
                ))
                db.commit()
    cookie_consent_state = get_consent_state(request, current_user)
    return templates.TemplateResponse(
        request,
        "checkout_success.html",
        {
            "current_user": current_user,
            "product": product,
            "session_id": session_id,
            "cookie_consent_state": cookie_consent_state,
              },
        )
@app.post("/cookie-consent")
async def set_cookie_consent(
    request: Request,
    value: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record cookie consent. Writes cookie for everyone, DB column for logged-in users."""
    if value not in ("accepted", "declined"):
        raise HTTPException(status_code=400, detail="Invalid consent value.")
    # DB write for logged-in users
    if current_user is not None:
        current_user.cookie_consent = (value == "accepted")
        current_user.cookie_consent_at = datetime.now(timezone.utc)
        current_user.cookie_consent_version = COOKIE_CONSENT_VERSION
        db.commit()
    # Cookie write for everyone
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie(
        key="cookie_consent",
        value=value,
        max_age=60 * 60 * 24 * 365,  # 12 months
        httponly=False,
        secure=True,
        samesite="lax",
    )
    return response
@app.get("/cancel", response_class=HTMLResponse)
async def checkout_cancel(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "checkout_cancel.html",
        {"current_user": current_user},
    )

# =========================================================
# PAID INTAKE WORKFLOW  (no auth required — public intake)
# =========================================================

@app.get("/intake", response_class=HTMLResponse)
async def intake_page(
    request: Request,
    session_id: str,
    service: str = "single",
):
    if service not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid service type.")

    if EVIDENTIX_DEV_MODE and session_id == "test":
        session = {"customer_details": {"email": "test@example.com"}}
    else:
        session = verify_checkout_session(session_id)

    return templates.TemplateResponse(
        request,
        "intake_form.html",
        {
            "session_id": session_id,
            "cookie_consent_state": cookie_consent_state,
            "service": service,
            "service_info": SERVICE_MAP[service],
            "customer_email": session.get("customer_details", {}).get("email", ""),
        },
    )


@app.post("/submit-intake", response_class=HTMLResponse)
async def submit_intake(
    request: Request,
    session_id: str = Form(...),
    service: str = Form(...),
    client_name: str = Form(...),
    client_email: str = Form(...),
    company_name: str = Form(""),
    matter_name: str = Form(...),
    case_reference: str = Form(""),
    narrative: str = Form(...),
    disclaimer_accepted: str = Form(...),
    web_detection_enabled: bool = Form(False),
    files: List[UploadFile] = File(...),
):
    if service not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid service type.")

    if EVIDENTIX_DEV_MODE and session_id == "test":
        session = {"customer_details": {"email": "test@example.com"}}
    else:
        session = verify_checkout_session(session_id)

    if disclaimer_accepted.lower() not in {"yes", "true", "on", "1"}:
        raise HTTPException(status_code=400, detail="Disclaimer must be accepted.")

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    max_files = SERVICE_MAP[service]["max_files"]
    if len(files) > max_files:
        raise HTTPException(
            status_code=400,
            detail=f"{SERVICE_MAP[service]['name']} allows up to {max_files} file(s).",
        )

    case_id = create_paid_case_id(service)
    matter_slug = safe_slug(matter_name)
    case_dir = CASES_DIR / f"{case_id}_{matter_slug}"
    uploads_dir = case_dir / "uploads"
    reports_dir = case_dir / "reports"
    audit_dir = case_dir / "audit"

    uploads_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    uploaded_items = []

    for up in files:
        original_name = Path(up.filename).name
        target_path = uploads_dir / original_name

        with target_path.open("wb") as buffer:
            shutil.copyfileobj(up.file, buffer)

        uploaded_items.append(
            {
                "filename": original_name,
                "stored_path": str(target_path),
                "content_type": up.content_type,
                "size_bytes": target_path.stat().st_size,
                "sha256": sha256_file(target_path),
            }
        )

    intake_data = {
        "case_id": case_id,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "service": service,
        "service_name": SERVICE_MAP[service]["name"],
        "stripe_session_id": session_id,
        "stripe_customer_email": session.get("customer_details", {}).get("email"),
        "stripe_amount_total": session.get("amount_total"),
        "stripe_currency": session.get("currency"),
        "client": {
            "name": client_name,
            "email": client_email,
            "company_name": company_name,
        },
        "matter": {
            "matter_name": matter_name,
            "case_reference": case_reference,
            "narrative": narrative,
        },
        "files": uploaded_items,
        "web_detection_enabled": web_detection_enabled,
        "status": "intake_received",
    }

    with (case_dir / "intake.json").open("w", encoding="utf-8") as f:
        json.dump(intake_data, f, indent=2)
    log_audit_event(
        event_type="intake_submitted",
        case_id=case_id,
        user=client_email,
        ip_address=request.client.host,
        notes=f"Paid intake received: {SERVICE_MAP[service]['name']}, {len(uploaded_items)} file(s)",
        extra={
            "stripe_session_id": session_id,
            "service": service,
            "file_count": len(uploaded_items),
            "web_detection_enabled": web_detection_enabled,
        },
    )

    if service == "single" and len(uploaded_items) == 1:
        image_path = uploaded_items[0]["stored_path"]
        analyze_file(image_path, case_dir=str(case_dir), web_detection_enabled=web_detection_enabled)

    return templates.TemplateResponse(
        request,
        "intake_success.html",
        {
            "case_id": case_id,
            "service_name": SERVICE_MAP[service]["name"],
            "file_count": len(uploaded_items),
            "client_email": client_email,
        },
    )
# =========================================================
# INTEGRITY CERTIFICATE  (login required)
# =========================================================

@app.api_route("/generate/integrity/{case_id}/{evidence_id}", methods=["GET", "POST"])
async def generate_integrity_certificate_route(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from app.pdf_integrity_certificate import generate_integrity_certificate

    # Verify case ownership
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    # Load evidence item
    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Evidence item not found.")

    # 3c: entitlement gate. Unpaid -> redirect into file-aware checkout.
    from app.entitlements import assert_cert_entitlement
    try:
        assert_cert_entitlement(db, current_user, case_id, evidence_id)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(
                url=("/checkout/integrity_certificate"
                     f"?case_id={quote(case_id)}&evidence_id={quote(evidence_id)}"),
                status_code=303,
            )
        raise

    # Load report data
    report = {}
    if item.json_report:
        try:
            report = json.loads(get_file(item.json_report).decode("utf-8"))
        except Exception:
            report = {}
    report["file_name"] = report.get("file_name") or item.file_name
    report["sha256"] = report.get("sha256") or item.sha256
    try:
        report["analysis_date"] = datetime.fromisoformat(str(item.analysis_date or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))).strftime("%B %d, %Y at %H:%M:%S UTC")
    except Exception:
        report["analysis_date"] = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M:%S UTC")
    if "metadata" not in report:
        report["metadata"] = {}
    if not report["metadata"].get("mime_type"):
        ext = item.file_name.rsplit(".", 1)[-1].upper() if item.file_name and "." in item.file_name else ""
        report["metadata"]["mime_type"] = f"{ext} file" if ext else "Unknown"


    base_url = str(request.base_url).rstrip("/")

    # Reconstruct c2pa dict from stored EvidenceItem columns (populated at upload).
    # This ensures the certificate reports the C2PA findings captured at the time
    # of analysis, not a re-analysis at certificate-generation time.
    # NOTE: stale DUPLICATE of c2pa_analysis._state_label \u2014 kept in sync by hand
    # for now; should be deduplicated by importing the canonical _state_label.
    _state_labels = {
        "VALID":       "Content Credentials Present and Verified",
        "INVALID":     "Content Credentials Present \u2014 Verification Failed",
        "SIGNED_UNRECOGNIZED_ISSUER": "Content Credentials Present \u2014 Valid Signature, Unrecognized Issuer",
        "ABSENT":      "No Content Credentials Detected",
        "UNAVAILABLE": "C2PA Analysis Unavailable",
    }
    _state = item.c2pa_state or "UNAVAILABLE"
    _analyzed_at_iso = (
        item.c2pa_analyzed_at.isoformat().replace("+00:00", "Z")
        if item.c2pa_analyzed_at else None
    )
    report["c2pa"] = {
        "state":                   _state,
        "state_label":             _state_labels.get(_state, "C2PA Analysis Unavailable"),
        "analyzed_at":             _analyzed_at_iso,
        "claim_generator":         item.c2pa_claim_generator,
        "claim_generator_version": item.c2pa_claim_generator_version,
        "signature_issuer":        item.c2pa_signature_issuer,
        "signature_time":          item.c2pa_signature_time,
        "signature_valid":         item.c2pa_signature_valid,
        "trust_list_status":       item.c2pa_trust_list_status,
        "revocation_status":       item.c2pa_revocation_status,
        "has_ai_generation":       item.c2pa_has_ai_generation,
        "has_ai_modification":     item.c2pa_has_ai_modification,
        "has_training_mining":     item.c2pa_has_training_mining,
        "ai_agents_found":         item.c2pa_ai_agents_found or [],
        "num_assertions":          item.c2pa_num_assertions,
        "num_ingredients":         item.c2pa_num_ingredients,
        "plain_english":           item.c2pa_plain_english or "Content Credentials analysis not available.",
    }

    from app.utils.audit_log import verify_chain
    try:
        chain_verified, _, _ = verify_chain(case_id)
    except Exception:
        chain_verified = None

    certificate_id, pdf_bytes = generate_integrity_certificate(

        report=report,
        case_id=case_id,
        evidence_id=evidence_id,
        generated_by=current_user.email,
        base_url=base_url,
        file_key=item.file_key,
        chain_verified=chain_verified,
    )

    # Upload PDF to S3
    pdf_key = upload_file(
        io.BytesIO(pdf_bytes),
        f"integrity_certificate_{certificate_id}.pdf",
        "application/pdf",
    )

    # Save certificate record
    cert = Certificate(
        certificate_id=certificate_id,
        type="integrity",
        case_id=case_id,
        evidence_id=evidence_id,
        generated_by=current_user.email,
        pdf_key=pdf_key,
        file_hash_at_generation=item.sha256,
    )
    db.add(cert)
    db.commit()

    # Log it
    log_audit_event(
        event_type="report_generated",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Integrity Certificate generated: {certificate_id}",
    )

    # Return the PDF directly
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=integrity_certificate_{certificate_id}.pdf"
        },
    )


@app.get("/verify/{certificate_id}", response_class=HTMLResponse)
async def verify_certificate(
    request: Request,
    certificate_id: str,
    db: Session = Depends(get_db),
):
    cert = db.query(Certificate).filter(
        Certificate.certificate_id == certificate_id
    ).first()

    if not cert:
        return templates.TemplateResponse(
            request,
            "verify.html",
            {"cert": None, "certificate_id": certificate_id},
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "verify.html",
        {
            "cert": {
                "certificate_id": cert.certificate_id,
                "type": cert.type,
                "case_id": cert.case_id,
                "evidence_id": cert.evidence_id,
                "file_hash_at_generation": cert.file_hash_at_generation,
                "created_at": cert.created_at.strftime("%B %d, %Y at %H:%M:%S UTC") if cert.created_at else "—",
            },
            "certificate_id": certificate_id,
        },
    )
# =========================================================
# WEB DETECTION  (login required)
# =========================================================

@app.get("/web-detection/{case_id}/{evidence_id}", response_class=HTMLResponse)
async def web_detection_consent(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found.")

    return templates.TemplateResponse(
        request,
        "web_detection_consent.html",
        {
            "case_id": case_id,
            "evidence_id": evidence_id,
            "item": item,
            "current_user": current_user,
        },
    )


@app.post("/web-detection/{case_id}/{evidence_id}", response_class=HTMLResponse)
async def web_detection_route(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from app.utils.web_detection import detect_web_presence
    import tempfile, os

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found.")

    # Download file from S3 to temp location
    raw_bytes = get_file(item.file_key)
    ext = (item.file_name or "file.bin").rsplit(".", 1)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        web_detection = detect_web_presence(tmp_path)
    finally:
        os.unlink(tmp_path)

    item.web_detection_enabled = True
    db.commit()

    log_audit_event(
        event_type="web_detection_consented",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"User consented to web detection via on-demand endpoint for {item.file_name}",
    )

    return templates.TemplateResponse(
        request,
        "web_detection.html",
        {
            "case_id": case_id,
            "evidence_id": evidence_id,
            "file_name": item.file_name,
            "web_detection": web_detection,
            "current_user": current_user,
        },
    )
# =========================================================
# DOWNLOAD HELPERS  (login required)
# =========================================================

@app.get("/download-case-file/{case_id}/{subfolder}/{timestamp}/{filename}")
async def download_case_file(
    case_id: str,
    subfolder: str,
    request: Request, 
    timestamp: str,
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    file_path = CASES_DIR / case_id / subfolder / timestamp / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    log_audit_event(
        event_type="file_downloaded",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"File downloaded: {filename}",
    )
    return FileResponse(str(file_path), filename=filename)

@app.get("/download-bundle/{case_id}/{evidence_id}")
async def download_bundle(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        zip_path = tmp.name

    with zipfile.ZipFile(zip_path, "w") as zipf:
        if item.file_key:
            url = generate_presigned_url(item.file_key)
            r = requests.get(url)
            zipf.writestr(item.file_name, r.content)

        if item.json_report:
            url = generate_presigned_url(item.json_report)
            r = requests.get(url)
            zipf.writestr("analysis_report.json", r.content)

        cert_row = (
            db.query(Certificate)
            .filter(
                Certificate.type == "integrity",
                Certificate.case_id == case_id,
                Certificate.evidence_id == evidence_id,
            )
            .order_by(Certificate.created_at.desc())
            .first()
        )
        if cert_row and cert_row.pdf_key:
            url = generate_presigned_url(cert_row.pdf_key)
            r = requests.get(url)
            zipf.writestr("integrity_certificate.pdf", r.content)
    log_audit_event(
        event_type="file_downloaded",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Evidence bundle downloaded: {case_id}_{evidence_id}_bundle.zip",
    )

    log_audit_event(
        event_type="report_downloaded",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Analysis report downloaded as part of evidence bundle",
    )

    return FileResponse(
        zip_path,
        filename=f"{case_id}_{evidence_id}_bundle.zip",
        media_type="application/zip",
    )
# =========================================================
# CUSTODY RECORD  (login required)
# =========================================================

@app.post("/generate/custody/{case_id}")
async def generate_custody_record_route(
    case_id: str,
    request: Request,
    scope: str = "case",
    evidence_id: Optional[str] = None,
    redacted: bool = True,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from app.pdf_custody_record import generate_custody_record
    from app.utils.audit_log import verify_chain
    from app.models import CustodyLog

    # Verify case ownership
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    if scope == "file" and not evidence_id:
        raise HTTPException(status_code=400, detail="evidence_id is required when scope=file.")

    # Pull custody events
    audit_query = db.query(CustodyLog).filter(CustodyLog.case_id == case_id)
    if scope == "file" and evidence_id:
        audit_query = audit_query.filter(CustodyLog.evidence_id == evidence_id)
    audit_rows = audit_query.order_by(CustodyLog.id.asc()).all()

    custody_events = [
        {
            "event_type":  row.action or "—",
            "timestamp":   row.created_at.isoformat() if row.created_at else "—",
            "user":        row.user_email or "—",
            "ip_address":  row.ip_address or "—",
            "evidence_id": row.evidence_id or "—",
            "notes":       row.detail or "",
        }
        for row in audit_rows
    ]

    # Pull evidence items
    evidence_query = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id)
    if scope == "file" and evidence_id:
        evidence_query = evidence_query.filter(EvidenceItem.evidence_id == evidence_id)
    evidence_rows = evidence_query.order_by(EvidenceItem.id.asc()).all()

    evidence_items = [
        {
            "evidence_id":               e.evidence_id,
            "file_name":                 e.file_name,
            "sha256":                    e.sha256,
            "file_key":                  e.file_key,
            "analysis_date":             e.analysis_date,
            "user":                      current_user.email,
            # C2PA Content Credentials (populated for image uploads)
            "c2pa_state":                e.c2pa_state,
            "c2pa_has_ai_generation":   e.c2pa_has_ai_generation,
            "c2pa_has_ai_modification": e.c2pa_has_ai_modification,
            "c2pa_signature_valid":     e.c2pa_signature_valid,
            "c2pa_claim_generator":     e.c2pa_claim_generator,
            "c2pa_signature_issuer":    e.c2pa_signature_issuer,
            "c2pa_signature_time":      e.c2pa_signature_time,
            "c2pa_plain_english":       e.c2pa_plain_english,
            "c2pa_analyzed_at":         e.c2pa_analyzed_at,
        }
        for e in evidence_rows
    ]

    # Chain verification
    try:
        chain_verified, _failed_id, _fail_msg = verify_chain(case_id)
        chain_event_count = len(custody_events)
    except Exception:
        chain_verified = None
        chain_event_count = len(custody_events)
 
    base_url = str(request.base_url).rstrip("/")

    record_id, pdf_bytes = generate_custody_record(
        case_id=case_id,
        case_name=case_obj.case_name,
        generated_by=current_user.email,
        custody_events=custody_events,
        evidence_items=evidence_items,
        scope=scope,
        evidence_id=evidence_id,
        chain_verified=chain_verified,
        chain_event_count=chain_event_count,
        redacted=redacted,
        base_url=base_url,
    )

    # Monitoring — chain failure alert
    if chain_verified is False:
        sub = get_active_monitoring_sub(current_user.id, db)
        if sub:
            send_chain_failure_alert(
                to_email=current_user.email,
                case_id=case_id,
                case_name=case_obj.case_name,
                record_id=record_id,
                base_url=str(request.base_url).rstrip("/"),
            )
    
    # Upload to S3
    pdf_key = upload_file(
        io.BytesIO(pdf_bytes),
        f"custody_record_{record_id}.pdf",
        "application/pdf",
    )

    # Save Certificate record
    cert = Certificate(
        certificate_id=record_id,
        type="custody",
        case_id=case_id,
        evidence_id=evidence_id,
        generated_by=current_user.email,
        pdf_key=pdf_key,
        chain_verified_at_generation=chain_verified,
        file_hash_at_generation=evidence_items[0]["sha256"] if evidence_items else None,
    )
    db.add(cert)
    db.commit()

    log_audit_event(
        event_type="custody_record_generated",
        case_id=case_id,
        evidence_id=evidence_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Custody Record generated: {record_id} (scope={scope}, redacted={redacted})",
    )

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=custody_record_{record_id}.pdf"
        },
    )


@app.get("/verify-custody/{record_id}", response_class=HTMLResponse)
async def verify_custody_record(
    request: Request,
    record_id: str,
    db: Session = Depends(get_db),
):
    cert = db.query(Certificate).filter(
        Certificate.certificate_id == record_id,
        Certificate.type == "custody",
    ).first()

    if not cert:
        return templates.TemplateResponse(
            request,
            "verify_custody.html",
            {"cert": None, "record_id": record_id},
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "verify_custody.html",
        {
            "cert": {
                "record_id":    cert.certificate_id,
                "type":         cert.type,
                "case_id":      cert.case_id,
                "evidence_id":  cert.evidence_id,
                "generated_by": cert.generated_by,
                "chain_verified": cert.chain_verified_at_generation,
                "created_at":   cert.created_at.strftime("%B %d, %Y at %H:%M:%S UTC") if cert.created_at else "—",
            },
            "record_id": record_id,
        },
    )
# =========================================================
# ADMIN — CLEAR CUSTODY LOG
# =========================================================

@app.post("/admin/clear-custody-log/{case_id}")
async def clear_custody_log(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import CustodyLog

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")

    db.query(CustodyLog).filter(CustodyLog.case_id == case_id).delete()
    db.commit()

    log_audit_event(
        event_type="custody_log_cleared",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Custody log cleared by admin",
    )

    return RedirectResponse(url=f"/cases/{case_id}", status_code=303)

# MONITORING — MONTHLY SUMMARY  (admin only)
# =========================================================

@app.post("/admin/send-monthly-summaries")
async def send_monthly_summaries(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.utils.audit_log import verify_chain
    from app.models import CustodyLog

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    period = datetime.now(timezone.utc).strftime("%B %Y")
    subs = db.query(Subscription).filter(
        Subscription.status == "active",
        Subscription.product.in_(["monitoring_small", "monitoring_standard", "monitoring_large"]),
    ).all()

    sent = 0
    for sub in subs:
        if not sub.user_id:
            continue
        user = db.query(User).filter(User.id == sub.user_id).first()
        if not user:
            continue
        cases = db.query(Case).filter(Case.user_id == sub.user_id).all()
        for case in cases:
            file_count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case.case_id).count()
            event_count = db.query(CustodyLog).filter(CustodyLog.case_id == case.case_id).count()
            tier_limit = TIER_LIMITS.get(sub.product, 25)
            try:
                chain_verified, _, _ = verify_chain(case.case_id)
            except Exception:
                chain_verified = None
            base_url = str(request.base_url).rstrip("/")
            send_monthly_summary(
                to_email=user.email,
                case_id=case.case_id,
                case_name=case.case_name,
                file_count=file_count,
                tier_limit=tier_limit,
                event_count=event_count,
                chain_verified=chain_verified,
                period=period,
                base_url=base_url,
            )
            sent += 1

    return {"status": "ok", "summaries_sent": sent}

@app.post("/delete-evidence/{case_id}/{evidence_id}")
async def delete_evidence(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from app.models import EvidenceItem
    evidence = db.query(EvidenceItem).filter(
        EvidenceItem.evidence_id == evidence_id,
        EvidenceItem.case_id == case_id,
    ).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found.")

    # Capture S3 key BEFORE deleting DB row
    file_key = evidence.file_key

    from app.models import FingerprintIndex
    db.query(FingerprintIndex).filter(FingerprintIndex.evidence_id == evidence_id).delete()

    db.delete(evidence)
    db.commit()

    # Delete S3 object (idempotent)
    delete_object(file_key)
    log_audit_event(
        event_type="evidence_deleted",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Evidence item {evidence_id} deleted by authenticated user",
    )
    return RedirectResponse(url=f"/cases/{case_id}?uploaded=1", status_code=303)

@app.post("/delete-all-evidence/{case_id}")
async def delete_all_evidence(
    case_id: str,
    request: Request,
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    # Gather S3 keys BEFORE deleting DB rows
    evidence_keys = [e.file_key for e in db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()]

    db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).delete()
    db.commit()

    # Delete S3 objects (idempotent)
    delete_objects(evidence_keys)

    log_audit_event(
        event_type="all_evidence_deleted",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="All evidence items deleted by authenticated user",
    )

    return RedirectResponse(url=f"/cases/{case_id}?uploaded=1", status_code=303)
# =========================================================
# REPORT FILE REDIRECT  (login required)
# =========================================================

@app.get("/report-file/{case_id}/{evidence_id}/{report_type}")
async def report_file_redirect(
    case_id: str,
    evidence_id: str,
    report_type: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    item = (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.case_id == case_id,
            EvidenceItem.evidence_id == evidence_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found.")

    if report_type == "json" and item.json_report:
        url = generate_presigned_url(item.json_report)
        return RedirectResponse(url=url, status_code=302)
    else:
        raise HTTPException(status_code=404, detail="Report not found.")

        
@app.get("/global-matches", response_class=HTMLResponse)
async def global_matches(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import EvidenceItem, Case
    cases = db.query(Case).order_by(Case.id.asc()).all()
    if not current_user.is_admin:
        cases = [c for c in cases if c.user_id == current_user.id]
    
    items = []
    for case in cases:
        evidence = db.query(EvidenceItem).filter(EvidenceItem.case_id == case.case_id).all()
        for e in evidence:
            items.append({
                "case_id": case.case_id,
                "case_name": case.case_name,
                "evidence_id": e.evidence_id,
                "file_name": e.file_name,
                "sha256": e.sha256,
                "analysis_date": e.analysis_date,
            })
    
    return templates.TemplateResponse(
        request,
        "global_matches.html",
        {"items": items, "current_user": current_user},
    )        
@app.get("/analyze-video", response_class=HTMLResponse)
async def analyze_video_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    cases = load_cases_for_user(current_user)
    return templates.TemplateResponse(
        request,
        "video_analyze.html",
        {"current_user": current_user, "cases": cases},
    )


@app.post("/analyze-video", response_class=HTMLResponse)
async def analyze_video_route(
    request: Request,
    case_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    from core.video_analyzer import analyze_video
    import uuid

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    case_dir = CASES_DIR / case_id
    upload_dir = case_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    evidence_id = str(uuid.uuid4())
    file_path = upload_dir / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file.file.seek(0)
    file_key = upload_file(file.file, file.filename, file.content_type)

    log_audit_event(
        event_type="file_uploaded",
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file.filename,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Video evidence file uploaded",
    )

    result, json_path, pdf_path = analyze_video(str(file_path), case_dir=str(case_dir))

    # Run C2PA analysis on the video file. The c2pa-python library uses the same
    # Rust engine for MP4/MOV that it uses for JPEG/PNG, so we call the same
    # analysis function. Defensive try/except - we never fail the upload because
    # of a C2PA library error.
    from app.c2pa_analysis import analyze_file as c2pa_analyze_file, summarize_for_certificate
    try:
        c2pa_result = c2pa_analyze_file(str(file_path))
        c2pa_data = summarize_for_certificate(c2pa_result)
    except Exception:
        c2pa_data = {"state": "UNAVAILABLE"}

    new_item = EvidenceItem(
        evidence_id=evidence_id,
        case_id=case_id,
        file_name=file.filename,
        file_key=file_key,
        json_report=json_path,
        sha256=result.get("sha256"),
        analysis_date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        # C2PA Content Credentials (16 columns - matches image analyze path)
        c2pa_state=c2pa_data.get("state"),
        c2pa_has_ai_generation=c2pa_data.get("has_ai_generation"),
        c2pa_has_ai_modification=c2pa_data.get("has_ai_modification"),
        c2pa_signature_valid=c2pa_data.get("signature_valid"),
        c2pa_claim_generator=c2pa_data.get("claim_generator"),
        c2pa_signature_issuer=c2pa_data.get("signature_issuer"),
        c2pa_signature_time=c2pa_data.get("signature_time"),
        c2pa_plain_english=c2pa_data.get("plain_english"),
        c2pa_analyzed_at=_parse_c2pa_analyzed_at(c2pa_data.get("analyzed_at")),
        c2pa_claim_generator_version=c2pa_data.get("claim_generator_version"),
        c2pa_num_assertions=c2pa_data.get("num_assertions"),
        c2pa_num_ingredients=c2pa_data.get("num_ingredients"),
        c2pa_trust_list_status=c2pa_data.get("trust_list_status"),
        c2pa_revocation_status=c2pa_data.get("revocation_status"),
        c2pa_ai_agents_found=c2pa_data.get("ai_agents_found"),
        c2pa_has_training_mining=c2pa_data.get("has_training_mining"),
    )

    log_audit_event(
        event_type="analysis_completed",
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file.filename,
        sha256=result.get("sha256"),
        user=current_user.email,
        ip_address=request.client.host,
        notes="Video forensic analysis and report generated",
        extra={
            "json_report": json_path,
            "pdf_report": pdf_path,
            "s3_file_key": file_key,
        },
    )

    db.add(new_item)
    db.commit()

    return templates.TemplateResponse(
        request,
        "video_result.html",
        {
            "result": result,
            "case_id": case_id,
            "current_user": current_user,
        },
    )
@app.get("/compare-video", response_class=HTMLResponse)
async def compare_video_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    cases = load_cases_for_user(current_user)
    return templates.TemplateResponse(
        request,
        "video_compare.html",
        {"current_user": current_user, "cases": cases},
    )


@app.post("/compare-video", response_class=HTMLResponse)
async def compare_video_route(
    request: Request,
    original_file: UploadFile = File(...),
    suspect_file: UploadFile = File(...),
    current_user: User = Depends(require_verified_email),
    db: Session = Depends(get_db),
):
    # Comparison credit gate: 402 into checkout when no unconsumed credit.
    from app.entitlements import assert_compare_entitlement, consume_compare_credit
    try:
        _compare_credit = assert_compare_entitlement(db, current_user)
    except HTTPException as e:
        if e.status_code == 402:
            return RedirectResponse(url="/checkout/comparison", status_code=303)
        raise
    from core.video_analyzer import analyze_video
    from core.video_compare import compare_frame_sets

    temp_dir = UPLOADS_DIR / "temp_video_compare"
    temp_dir.mkdir(parents=True, exist_ok=True)

    original_path = temp_dir / original_file.filename
    suspect_path = temp_dir / suspect_file.filename

    with original_path.open("wb") as f:
        f.write(await original_file.read())
    with suspect_path.open("wb") as f:
        f.write(await suspect_file.read())

    original_result = analyze_video(str(original_path))
    suspect_result = analyze_video(str(suspect_path))

    matches = compare_frame_sets(
        original_result["frame_hashes"],
        suspect_result["frame_hashes"],
    )
    consume_compare_credit(db, _compare_credit)
    unique_matching = len(set(m["frame1"] for m in matches))
    match_pct = round(
    unique_matching / max(len(original_result["frame_hashes"]), 1) * 100, 1
    )
    match_pct = min(match_pct, 100.0)

    log_audit_event(
        event_type="video_comparison_performed",
        case_id="COMPARE",
        user=current_user.email,
        ip_address=request.client.host,
        notes=f"Video comparison: {original_file.filename} vs {suspect_file.filename}",
    )

    return templates.TemplateResponse(
        request,
        "video_compare_result.html",
        {
            "original": original_result,
            "suspect": suspect_result,
            "matches": matches,
            "match_pct": match_pct,
            "current_user": current_user,
        },
    )

from app.external_routes import external_router
app.include_router(external_router)