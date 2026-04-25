import json
import os
import shutil
import hashlib
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from sqlalchemy import event
from sqlalchemy import event
import stripe
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, Response
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.analyzer import analyze_file
from app.utils.audit_log import log_audit_event
from app.db import SessionLocal, engine
from app.models import Base, Case, Certificate, EvidenceItem, Payment, Subscription, User
from app.storage import upload_file
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_optional_user,
    get_db,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

from core.batch_scan import scan_folder
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


def generate_case_id(existing_cases):
    next_number = len(existing_cases) + 1
    return f"CASE-{next_number:04d}"


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


def create_paid_case_id(service: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{service.upper()}-{ts}"


def verify_checkout_session(session_id: str):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe secret key not configured.")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unable to verify Stripe session: {e}")
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
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
    db: Session = Depends(get_db),
):
    error = None

    if password != password_confirm:
        error = "Passwords do not match."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif db.query(User).filter(User.email == email.lower().strip()).first():
        error = "An account with that email already exists."

    if error:
        return templates.TemplateResponse(
            request, "register.html", {"error": error}, status_code=400
        )

    user = User(
        email=email.lower().strip(),
        hashed_password=hash_password(password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    resp = RedirectResponse(url="/", status_code=303)
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
async def login_page(request: Request, next: Optional[str] = None):
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": next})

@app.get("/pricing")
async def pricing(request: Request):
    return templates.TemplateResponse(request, "pricing.html", {})

@app.get("/sample")
async def sample():
    return RedirectResponse(url="https://evidentix-files-ken01.s3.us-west-2.amazonaws.com/04.06.26+Sample+for+Display.pdf", status_code=303)

@app.get("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})

@app.get("/terms")
async def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})

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
    resp = RedirectResponse(url=redirect_to, status_code=303)
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


# =========================================================
# BASIC CASE WORKFLOW  (all routes now require login)
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    cases = load_cases_for_user(current_user)
    deleted = request.query_params.get("deleted")

    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "cases": cases,
            "current_user": current_user,
            "message": "Case deleted successfully." if deleted else None,
        },
    )


@app.post("/create-case", response_class=HTMLResponse)
async def create_case(
    request: Request,
    case_name: str = Form(...),
    description: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_cases = db.query(Case).order_by(Case.id.asc()).all()
    case_id = generate_case_id(existing_cases)

    new_case = Case(
        case_id=case_id,
        case_name=case_name,
        description=description,
        user_id=current_user.id,
    )
    db.add(new_case)
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
        },
    )


@app.post("/delete-case/{case_id}")

async def delete_case(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    case_obj = db.query(Case).filter(Case.case_id == case_id).first()

    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")

    assert_case_ownership(case_obj, current_user)

    log_audit_event(
        event_type="case_deleted",
        case_id=case_id,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Case and all evidence deleted by authenticated user",
    )

    db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).delete()
    db.delete(case_obj)
    db.commit()
  
    case_dir = CASES_DIR / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)

    return RedirectResponse(url="/?deleted=1", status_code=303)


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

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
    )
    log_audit_event(
        event_type="analysis_completed",
        case_id=case_id,
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

    return RedirectResponse(url=f"/cases/{case_id}?uploaded=1", status_code=303)

@app.get("/evidence-file/{case_id}/{evidence_id}")
async def evidence_file_redirect(
    case_id: str,
    evidence_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.storage import generate_presigned_url

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
    current_user: User = Depends(get_current_user),
):
    safe_case_name = safe_slug(case_name)
    case_path = REPORTS_DIR / safe_case_name
    case_path.mkdir(parents=True, exist_ok=True)

    original_path = case_path / original_file.filename
    suspected_path = case_path / suspected_file.filename

    with original_path.open("wb") as f:
        shutil.copyfileobj(original_file.file, f)

    with suspected_path.open("wb") as f:
        shutil.copyfileobj(suspected_file.file, f)

    comparison = compare_two_files(str(original_path), str(suspected_path), str(case_path))

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
            "comparison": comparison,
            "case_name": case_name,
            "client_name": client_name,
            "case_notes": case_notes,
            "current_user": current_user,
        },
    )

@app.post("/compare-against-case", response_class=HTMLResponse)
async def compare_against_case_route(
    request: Request,
    current_user: User = Depends(get_current_user),
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

    # Ownership check
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    upload_dir = PROJECT_ROOT / "temp_uploads"
    upload_dir.mkdir(exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / safe_filename

    with file_path.open("wb") as f:
        f.write(await file.read())

    try:
        result = compare_against_case(str(file_path), case_id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if case_obj:
        assert_case_ownership(case_obj, current_user)

    compare_dir = CASES_DIR / case_id / "comparisons"
    compare_dir.mkdir(parents=True, exist_ok=True)

    suspect_path = compare_dir / suspect_file.filename

    with suspect_path.open("wb") as buffer:
        buffer.write(await suspect_file.read())

    result = compare_against_case(str(suspect_path), case_id=case_id)

log_audit_event(
        event_type="case_comparison_completed",
        case_id=case_id,
        file_name=suspect_file.filename,
        user=current_user.email,
        ip_address=request.client.host,
        notes="Suspect image compared against evidence in selected case",
        extra={
            "best_match_file": result.get("comparison", {}).get("original_file") if result.get("comparison") else None,
            "similarity_score": result.get("comparison", {}).get("similarity_score") if result.get("comparison") else None,
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
            "comparison": result.get("comparison"),
            "matches": result.get("matches", []),
            "current_user": current_user,
        },
    )

@app.post("/compare-global", response_class=HTMLResponse)
async def compare_global_route(
    request: Request,
    suspect_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    temp_dir = UPLOADS_DIR / "temp_compare"
    temp_dir.mkdir(parents=True, exist_ok=True)

    suspect_path = temp_dir / suspect_file.filename

    with suspect_path.open("wb") as buffer:
        buffer.write(await suspect_file.read())

    result = compare_against_all_cases(str(suspect_path))

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
            "suspect_file": suspect_file.filename,
            "suspect_phash": result.get("suspect_phash"),
            "matches": result.get("matches", []),
            "current_user": current_user,
        },
    )

# =========================================================
# BATCH SCAN  (login required)
# =========================================================

@app.get("/batch-scan", response_class=HTMLResponse)
async def batch_scan_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "batch_scan.html", {"current_user": current_user})


@app.post("/batch-scan", response_class=HTMLResponse)
async def batch_scan_route(
    request: Request,
    folder_path: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    if not os.path.exists(folder_path):
        return HTMLResponse("Folder not found", status_code=404)

    results = scan_folder(folder_path)

    return templates.TemplateResponse(
        request,
        "batch_scan_result.html",
        {"folder": folder_path, "results": results, "current_user": current_user},
    )


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
    current_user: User = Depends(get_current_user),
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
    data_object = event["data"]["object"]

    # Idempotency guard — skip if we've already processed this event
    existing = db.query(Payment).filter(Payment.stripe_event_id == event_id).first()
    if existing:
        return {"status": "already_processed"}

    if event_type == "checkout.session.completed":
        customer_details = data_object.get("customer_details") or {}
        metadata = data_object.get("metadata") or {}

        payment = Payment(
            stripe_session_id=data_object["id"],
            stripe_event_id=event_id,
            stripe_customer_email=customer_details.get("email"),
            stripe_amount_total=data_object.get("amount_total"),
            stripe_currency=data_object.get("currency"),
            product=metadata.get("product"),
            status="paid",
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
                sub.updated_at = datetime.utcnow()
                db.commit()
            else:
                # First invoice.paid for this subscription — create the record
                stripe_sub = stripe.Subscription.retrieve(subscription_id)
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
            sub.updated_at = datetime.utcnow()
            db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription_id = data_object.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()

        if sub:
            sub.status = "canceled"
            sub.updated_at = datetime.utcnow()
            db.commit()

    elif event_type == "invoice.payment_failed":
        subscription_id = data_object.get("subscription")
        if subscription_id:
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()

            if sub:
                sub.status = "past_due"
                sub.updated_at = datetime.utcnow()
                db.commit()

    return {"status": "ok"}

# =========================================================
# STRIPE CHECKOUT ROUTES
# =========================================================
STRIPE_PRICES = {
    # Active SKUs
    "single": "price_1THUZ2HVHQNKUlwkBfHnsoDj",
    "video_single": "price_1TIqApHVHQNKUlwksbqqdsqA",
    "bundle": "price_1THUiNHVHQNKUlwkJG0v91C7",
    "video_image_bundle": "price_1TIqE7HVHQNKUlwk8v4FmJnP",
    "video_bundle": "price_1TIqCcHVHQNKUlwk6tJXz5Uo",
    "professional": "price_1THV2DHVHQNKUlwkZ5lyCBsE",
    "firm": "price_1THV6cHVHQNKUlwkViPyHk4f",

    # New Phase 2 SKUs — replace placeholder values with real Stripe price IDs
    # after creating them in the Stripe dashboard
    "integrity_certificate": "price_1TPknOHVHQNKUlwkTbhQdEgN",
    "custody_record": "price_1TPmDkHVHQNKUlwkj0AweJ9g",
    "monitoring_small": "price_1TPmFhHVHQNKUlwkRHoGFIyF",
    "monitoring_standard": "price_1TPmGvHVHQNKUlwkfr5LTk9G",
    "monitoring_large": "price_1TPmISHVHQNKUlwkcyt08yd4",

    # Retired — do not use in new checkouts
    # "integrity": "price_1TIqGdHVHQNKUlwk4oPa5cRp",
}

# Subscription products — used to determine checkout mode
SUBSCRIPTION_PRODUCTS = {
    "professional", "firm", "monitoring_small", "monitoring_standard", "monitoring_large"
}

STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")


@app.get("/checkout/{product}", response_class=HTMLResponse)
async def checkout(
    request: Request,
    product: str,
    current_user: User = Depends(get_current_user),
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
        success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}&product={product}",
        cancel_url=f"{base_url}/cancel",
        customer_email=current_user.email,
        allow_promotion_codes=True,
        metadata={"product": product},
    )

    return RedirectResponse(url=session.url, status_code=303)


@app.get("/success", response_class=HTMLResponse)
async def checkout_success(
    request: Request,
    session_id: str = "",
    product: str = "",
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "checkout_success.html",
        {
            "current_user": current_user,
            "product": product,
            "session_id": session_id,
        },
    )


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

    if session_id == "test":
        session = {"customer_details": {"email": "test@example.com"}}
    else:
        session = verify_checkout_session(session_id)

    return templates.TemplateResponse(
        request,
        "intake_form.html",
        {
            "session_id": session_id,
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
    files: List[UploadFile] = File(...),
):
    if service not in SERVICE_MAP:
        raise HTTPException(status_code=400, detail="Invalid service type.")

    if session_id == "test":
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
        "created_utc": datetime.utcnow().isoformat(),
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
        },
    )

    with (audit_dir / "intake_submitted.json").open("w", encoding="utf-8") as f:
        json.dump(audit_event, f, indent=2)

    if service == "single" and len(uploaded_items) == 1:
        image_path = uploaded_items[0]["stored_path"]
        analyze_file(image_path, case_dir=str(case_dir))

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

@app.post("/generate/integrity/{case_id}/{evidence_id}")
async def generate_integrity_certificate_route(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.pdf_integrity_certificate import generate_integrity_certificate
    from app.storage import upload_file as s3_upload
    import io

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

    # Load report data
    report = {}
    if item.json_report:
        try:
            from app.storage import get_file
            report = json.loads(get_file(item.json_report).decode("utf-8"))
        except Exception:
            report = {}

    report["file_name"] = report.get("file_name") or item.file_name
    report["sha256"] = report.get("sha256") or item.sha256
    report["analysis_date"] = report.get("analysis_date") or (
        item.analysis_date or datetime.utcnow().isoformat()
    )
    base_url = str(request.base_url).rstrip("/")

    # Run C2PA analysis and inject into report
    try:
        from app.c2pa_analysis import analyze_file, summarize_for_certificate
        from app.storage import get_file as s3_get_file
        import tempfile, os
        raw_bytes = s3_get_file(item.file_key)
        ext = (item.file_name or "file.bin").rsplit(".", 1)[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        c2pa_result = analyze_file(tmp_path)
        os.unlink(tmp_path)
        report["c2pa"] = summarize_for_certificate(c2pa_result)
    except Exception as e:
        report["c2pa"] = {"state": "UNAVAILABLE", "state_label": "C2PA Analysis Unavailable", "plain_english": f"Analysis could not be completed: {str(e)}", "error_detail": str(e)}

    certificate_id, pdf_bytes = generate_integrity_certificate(

        report=report,
        case_id=case_id,
        evidence_id=evidence_id,
        generated_by=current_user.email,
        base_url=base_url,
    )

    # Upload PDF to S3
    pdf_key = s3_upload(
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
# DOWNLOAD HELPERS  (login required)
# =========================================================

@app.get("/download-case-file/{case_id}/{subfolder}/{timestamp}/{filename}")
async def download_case_file(
    case_id: str,
    subfolder: str,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.storage import generate_presigned_url

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

        if item.pdf_report:
            url = generate_presigned_url(item.pdf_report)
            r = requests.get(url)
            zipf.writestr("analysis_report.pdf", r.content)
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
