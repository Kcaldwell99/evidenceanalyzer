
# =========================================================
# VIDEO COMPARISON ROUTES
# Paste this block into main.py just after the
# # VIDEO ANALYSIS ROUTES section
# =========================================================

from app.video_compare import compare_videos


@app.get("/compare-video", response_class=HTMLResponse)
async def video_compare_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Case).order_by(Case.id.asc())
    if not current_user.is_admin:
        query = query.filter(Case.user_id == current_user.id)
    cases = query.all()

    return templates.TemplateResponse(
        request,
        "video_compare.html",
        {
            "current_user": current_user,
            "cases": [{"case_id": c.case_id, "case_name": c.case_name} for c in cases],
            "max_size_mb": MAX_VIDEO_SIZE // (1024 * 1024),
        },
    )


@app.post("/compare-video", response_class=HTMLResponse)
async def video_compare_submit(
    request: Request,
    case_id: str = Form(...),
    video_a: UploadFile = File(...),
    video_b: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate ownership
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    case_dir = CASES_DIR / case_id
    compare_dir = case_dir / "comparisons"
    compare_dir.mkdir(parents=True, exist_ok=True)

    # Save both videos
    content_a = await video_a.read()
    content_b = await video_b.read()

    if len(content_a) > MAX_VIDEO_SIZE or len(content_b) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"One or both files exceed the {MAX_VIDEO_SIZE // (1024*1024)}MB limit.",
        )

    path_a = compare_dir / video_a.filename
    path_b = compare_dir / video_b.filename

    with path_a.open("wb") as f:
        f.write(content_a)
    with path_b.open("wb") as f:
        f.write(content_b)

    log_audit_event(
        event_type="video_comparison_started",
        case_id=case_id,
        file_name=f"{video_a.filename} vs {video_b.filename}",
        user=current_user.email,
        notes="Video comparison analysis started",
    )

    try:
        report = compare_videos(
            str(path_a),
            str(path_b),
            case_dir=str(case_dir),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

    log_audit_event(
        event_type="video_comparison_completed",
        case_id=case_id,
        file_name=f"{video_a.filename} vs {video_b.filename}",
        user=current_user.email,
        notes="Video comparison analysis completed",
        extra={
            "peak_similarity": report.get("summary", {}).get("peak_similarity", 0),
            "phase1_matches": report.get("summary", {}).get("phase1_matches", 0),
            "overall_assessment": report.get("summary", {}).get("overall_assessment", ""),
        },
    )

    return templates.TemplateResponse(
        request,
        "video_compare_result.html",
        {
            "current_user": current_user,
            "case_id": case_id,
            "report": report,
        },
    )
