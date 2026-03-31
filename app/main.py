import json
import os
import shutil
import hashlib
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

import requests
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

app = FastAPI()

# =========================
# PATHS
# =========================

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

CASES_DIR = PROJECT_ROOT / "cases"
REPORTS_DIR = PROJECT_ROOT / "reports"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

CASES_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.mount("/case-files", StaticFiles(directory=str(CASES_DIR)), name="case-files")
app.mount("/report-files", StaticFiles(directory=str(REPORTS_DIR)), name="report-files")

# =========================
# HELPERS
# =========================

def load_cases():
    db = SessionLocal()
    try:
        cases = db.query(Case).order_by(Case.id.asc()).all()
        return [
            {
                "case_id": c.case_id,
                "case_name": c.case_name,
                "description": c.description or "",
            }
            for c in cases
        ]
    finally:
        db.close()


def generate_case_id(existing_cases):
    return f"CASE-{len(existing_cases)+1:04d}"


def create_case_folder(case_id: str):
    case_dir = CASES_DIR / case_id
    (case_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (case_dir / "reports").mkdir(parents=True, exist_ok=True)
    return case_dir


# =========================
# HOME
# =========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cases = load_cases()
    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "cases": cases,
        },
    )


# =========================
# CREATE CASE
# =========================

@app.post("/create-case", response_class=HTMLResponse)
async def create_case(
    request: Request,
    case_name: str = Form(...),
    description: str = Form(""),
):
    db = SessionLocal()
    try:
        existing_cases = db.query(Case).all()
        case_id = generate_case_id(existing_cases)

        db.add(Case(
            case_id=case_id,
            case_name=case_name,
            description=description
        ))
        db.commit()

        create_case_folder(case_id)

        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


# =========================
# DELETE CASE
# =========================

@app.post("/delete-case/{case_id}")
async def delete_case(case_id: str):
    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_id == case_id).first()
        if not case:
            raise HTTPException(404)

        db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).delete()
        db.delete(case)
        db.commit()

        case_dir = CASES_DIR / case_id
        if case_dir.exists():
            shutil.rmtree(case_dir)

        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


# =========================
# ANALYZE FILE
# =========================

@app.post("/analyze")
async def analyze_file_route(
    case_id: str = Form(...),
    file: UploadFile = File(...),
):
    case_dir = CASES_DIR / case_id
    upload_dir = case_dir / "uploads"
    upload_dir.mkdir(exist_ok=True)

    file_path = upload_dir / file.filename

    with file_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    analyze_file(str(file_path), case_dir=str(case_dir))

    return RedirectResponse(f"/cases/{case_id}", status_code=303)


# =========================
# CASE DETAIL
# =========================

@app.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail(request: Request, case_id: str):
    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_id == case_id).first()
        evidence = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()

        return templates.TemplateResponse(
            "case_detail.html",
            {
                "request": request,
                "case": case,
                "evidence_items": evidence,
            },
        )
    finally:
        db.close()


# =========================
# COMPARE
# =========================

@app.post("/compare-against-case", response_class=HTMLResponse)
async def compare_against_case_route(request: Request):
    form = await request.form()
    case_id = form.get("case_id")
    file = form.get("file")

    temp_dir = UPLOADS_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)

    temp_path = temp_dir / file.filename

    with temp_path.open("wb") as f:
        f.write(await file.read())

    result = compare_against_case(str(temp_path), case_id)

    return templates.TemplateResponse(
        "compare_result.html",
        {
            "request": request,
            "result": result,
        },
    )