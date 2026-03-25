import json
import os
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List

import stripe
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.analyzer import analyze_file
from app.utils.audit_log import log_audit_event
from app.db import SessionLocal, engine
from app.models import Base, Case, EvidenceItem
from app.storage import upload_file

from core.batch_scan import scan_folder
from core.compare_files import compare_two_files, compare_against_case, compare_against_all_cases
from core.copyright_lookup import build_copyright_search_link
from sqlalchemy import text


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

app = FastAPI()
Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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

def load_cases():
    db = SessionLocal()
    try:
        cases = db.query(Case).order_by(Case.id.asc()).all()
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


# =========================================================
# BASIC CASE WORKFLOW
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    cases = load_cases()

    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "cases": cases,
        },
    )
   
@app.post("/create-case", response_class=HTMLResponse)
async def create_case(
    request: Request,
    case_name: str = Form(...),
    description: str = Form(""),
):
    db = SessionLocal()
    try:
        existing_cases = db.query(Case).order_by(Case.id.asc()).all()
        case_id = generate_case_id(existing_cases)

        new_case = Case(
            case_id=case_id,
            case_name=case_name,
            description=description,
        )
        db.add(new_case)
        db.commit()

        create_case_folder(case_id)

        updated_data = load_cases()

        return templates.TemplateResponse(
            request,
            "upload.html",
    {
                "cases": updated_data,
                "message": f"Case created successfully: {case_id}",
    },
)
        
    finally:
        db.close()


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    db = SessionLocal()
    try:
        cases = db.query(Case).order_by(Case.id.asc()).all()
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
            {
                "items": items,
            },
        )
    finally:
        db.close()


@app.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail(request: Request, case_id: str):
    uploaded = request.query_params.get("uploaded")

    db = SessionLocal()
    try:
        case_obj = db.query(Case).filter(Case.case_id == case_id).first()

        if not case_obj:
            return HTMLResponse(f"<h1>Case {case_id} not found</h1>", status_code=404)

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
            },
        )
    finally:
        db.close()


@app.post("/analyze")
async def analyze_file_route(
    request: Request,
    case_id: str = Form(...),
    file: UploadFile = File(...),
):
    case_dir = CASES_DIR / case_id
    case_upload_dir = case_dir / "uploads"
    case_upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = case_upload_dir / file.filename

    # Save locally first so analyze_file can read it
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Reset stream before uploading to S3
    file.file.seek(0)

    file_key = upload_file(file.file, file.filename, file.content_type)
    print("Uploaded to S3:", file_key)

    log_audit_event(
        event_type="file_uploaded",
        case_id=case_id,
        file_name=file.filename,
        user="system",
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
        user="system",
        notes="Image analysis and forensic report generated",
        extra={
            "json_report": json_path,
            "pdf_report": pdf_path,
            "s3_file_key": file_key,
        },
    )

    return RedirectResponse(
        url=f"/cases/{case_id}?uploaded=1",
        status_code=303,
    )
@app.get("/evidence-file/{case_id}/{evidence_id}")
async def evidence_file_redirect(case_id: str, evidence_id: str):
    from app.storage import generate_presigned_url

    db = SessionLocal()
    try:
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

        url = generate_presigned_url(item.file_key)
        return RedirectResponse(url=url, status_code=302)
    finally:
        db.close()
# =========================================================
# COMPARISON WORKFLOW
# =========================================================

@app.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request):
    return templates.TemplateResponse(
        request,
        "compare.html",
        {},
    )


@app.post("/compare", response_class=HTMLResponse)
async def compare_submit(
    request: Request,
    case_name: str = Form(...),
    client_name: str = Form(""),
    case_notes: str = Form(""),
    original_file: UploadFile = File(...),
    suspected_file: UploadFile = File(...),
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

    return templates.TemplateResponse(
        request,
        "compare_result.html",
        {
            "comparison": comparison,
            "case_name": case_name,
            "client_name": client_name,
            "case_notes": case_notes,
        },
    )


@app.post("/compare-case", response_class=HTMLResponse)
async def compare_case_route(
    request: Request,
    case_id: str = Form(...),
    suspect_file: UploadFile = File(...),
):
    compare_dir = CASES_DIR / case_id / "comparisons"
    compare_dir.mkdir(parents=True, exist_ok=True)

    suspect_path = compare_dir / suspect_file.filename

    with suspect_path.open("wb") as buffer:
        buffer.write(await suspect_file.read())

    result = compare_against_case(str(suspect_path), case_id=case_id)

    comparison = result.get("comparison")
    matches = result.get("matches", [])

    log_audit_event(
        event_type="case_comparison_completed",
        case_id=case_id,
        file_name=suspect_file.filename,
        user="system",
        notes="Suspect image compared against evidence in selected case",
        extra={
            "best_match_file": comparison.get("original_file") if comparison else None,
            "best_match_evidence_id": comparison.get("best_match_evidence_id") if comparison else None,
            "similarity_score": comparison.get("similarity_score") if comparison else None,
            "match_count": len(matches),
        },
    )

    return templates.TemplateResponse(
        request,
        "compare_case_result.html",
        {
            "case_id": case_id,
            "suspect_file": suspect_file.filename,
            "suspect_phash": result.get("suspect_phash"),
            "comparison": comparison,
            "matches": matches,
        },
    )


@app.post("/compare-global", response_class=HTMLResponse)
async def compare_global_route(
    request: Request,
    suspect_file: UploadFile = File(...),
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
        user="system",
        notes="Image compared against all cases",
        extra={
            "match_count": len(result.get("matches", [])),
        },
    )

    return templates.TemplateResponse(
        request,
        "compare_global_result.html",
        {
            "suspect_file": suspect_file.filename,
            "suspect_phash": result.get("suspect_phash"),
            "matches": result.get("matches", []),
        },
    )


# =========================================================
# BATCH SCAN
# =========================================================

@app.get("/batch-scan", response_class=HTMLResponse)
async def batch_scan_page(request: Request):
    return templates.TemplateResponse(
        request,
        "batch_scan.html",
        {},
    )


@app.post("/batch-scan", response_class=HTMLResponse)
async def batch_scan_route(
    request: Request,
    folder_path: str = Form(...),
):
    if not os.path.exists(folder_path):
        return HTMLResponse("Folder not found", status_code=404)

    results = scan_folder(folder_path)

    return templates.TemplateResponse(
        request,
        "batch_scan_result.html",
        {
            "folder": folder_path,
            "results": results,
        },
    )


# =========================================================
# COPYRIGHT SEARCH
# =========================================================

@app.get("/copyright-search", response_class=HTMLResponse)
async def copyright_search_page(request: Request):
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
        },
    )


# =========================================================
# PAID INTAKE WORKFLOW
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

    audit_event = {
        "event": "intake_submitted",
        "utc": datetime.utcnow().isoformat(),
        "stripe_session_id": session_id,
        "service": service,
        "file_count": len(uploaded_items),
    }
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
# DOWNLOAD BUNDLE (NEW FEATURE)
# =========================================================

# =========================================================
# DOWNLOAD BUNDLE
# =========================================================

import zipfile
import tempfile
import requests

@app.get("/download-bundle/{case_id}/{evidence_id}")
async def download_bundle(case_id: str, evidence_id: str):
    from app.storage import generate_presigned_url

    db = SessionLocal()
    try:
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
                json_path = os.path.join("cases", case_id, item.json_report)
                if os.path.exists(json_path):
                    zipf.write(json_path, "analysis_report.json")

            if item.pdf_report:
                pdf_path = os.path.join("cases", case_id, item.pdf_report)
                if os.path.exists(pdf_path):
                    zipf.write(pdf_path, "analysis_report.pdf")

        return FileResponse(
            zip_path,
            filename=f"{case_id}_{evidence_id}_bundle.zip",
            media_type="application/zip",
        )

    finally:
        db.close()


# =========================================================
# OPTIONAL FILE DOWNLOAD HELPERS
# =========================================================

@app.get("/download-case-file/{case_id}/{subfolder}/{timestamp}/{filename}")
async def download_case_file(case_id: str, subfolder: str, timestamp: str, filename: str):
    file_path = CASES_DIR / case_id / subfolder / timestamp / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(str(file_path), filename=filename)

# =========================================================
# DOWNLOAD BUNDLE
# =========================================================

import zipfile
import tempfile
import requests

@app.get("/download-bundle/{case_id}/{evidence_id}")
async def download_bundle(case_id: str, evidence_id: str):
    from app.storage import generate_presigned_url

    db = SessionLocal()
    try:
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
                json_path = os.path.join("cases", case_id, item.json_report)
                if os.path.exists(json_path):
                    zipf.write(json_path, "analysis_report.json")

            if item.pdf_report:
                pdf_path = os.path.join("cases", case_id, item.pdf_report)
                if os.path.exists(pdf_path):
                    zipf.write(pdf_path, "analysis_report.pdf")

        return FileResponse(
            zip_path,
            filename=f"{case_id}_{evidence_id}_bundle.zip",
            media_type="application/zip",
        )

    finally:
        db.close()


# =========================================================
# OPTIONAL FILE DOWNLOAD HELPERS
# =========================================================

@app.get("/download-case-file/{case_id}/{subfolder}/{timestamp}/{filename}")
async def download_case_file(case_id: str, subfolder: str, timestamp: str, filename: str):
    file_path = CASES_DIR / case_id / subfolder / timestamp / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(str(file_path), filename=filename)

# =========================================================
# OPTIONAL FILE DOWNLOAD HELPERS
# =========================================================

#if not os.getenv("ALLOW_FREE_DOWNLOADS", "false") == "true":
#    raise HTTPException(status_code=403, detail="Payment required to download bundle.")


@app.get("/download-case-file/{case_id}/{subfolder}/{timestamp}/{filename}")
async def download_case_file(case_id: str, subfolder: str, timestamp: str, filename: str):
    file_path = CASES_DIR / case_id / subfolder / timestamp / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(str(file_path), filename=filename)
