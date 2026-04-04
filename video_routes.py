
# =========================================================
# VIDEO ANALYSIS ROUTES
# Paste this block into main.py just before the
# # BATCH SCAN section
# =========================================================

from app.video_analyzer import (
    analyze_video,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_VIDEO_MIMETYPES,
    MAX_VIDEO_SIZE,
    check_ffmpeg,
)

VIDEO_STRIPE_PRICES = {
    "video_single": "price_VIDEO_SINGLE_ID",   # replace with real price ID
    "video_bundle": "price_VIDEO_BUNDLE_ID",   # replace with real price ID
    "video_image":  "price_VIDEO_IMAGE_ID",    # replace with real price ID
}


@app.get("/analyze-video", response_class=HTMLResponse)
async def video_upload_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get user's cases for the dropdown
    query = db.query(Case).order_by(Case.id.asc())
    if not current_user.is_admin:
        query = query.filter(Case.user_id == current_user.id)
    cases = query.all()

    ffmpeg_available = check_ffmpeg()

    return templates.TemplateResponse(
        request,
        "video_upload.html",
        {
            "current_user": current_user,
            "cases": [{"case_id": c.case_id, "case_name": c.case_name} for c in cases],
            "ffmpeg_available": ffmpeg_available,
            "max_size_mb": MAX_VIDEO_SIZE // (1024 * 1024),
        },
    )


@app.post("/analyze-video", response_class=HTMLResponse)
async def video_upload_submit(
    request: Request,
    case_id: str = Form(...),
    video_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate ownership
    case_obj = db.query(Case).filter(Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found.")
    assert_case_ownership(case_obj, current_user)

    # Validate file type
    ext = Path(video_file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return templates.TemplateResponse(
            request,
            "video_upload.html",
            {
                "current_user": current_user,
                "error": f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
                "cases": [],
            },
            status_code=400,
        )

    # Save video to case uploads dir
    case_dir = CASES_DIR / case_id
    video_upload_dir = case_dir / "uploads"
    video_upload_dir.mkdir(parents=True, exist_ok=True)

    video_path = video_upload_dir / video_file.filename

    # Read and check size
    content = await video_file.read()
    if len(content) > MAX_VIDEO_SIZE:
        return templates.TemplateResponse(
            request,
            "video_upload.html",
            {
                "current_user": current_user,
                "error": f"File too large. Maximum size is {MAX_VIDEO_SIZE // (1024*1024)}MB.",
                "cases": [],
            },
            status_code=400,
        )

    with video_path.open("wb") as f:
        f.write(content)

    # Upload to S3
    import io
    file_key = upload_file(io.BytesIO(content), video_file.filename, video_file.content_type)

    log_audit_event(
        event_type="video_uploaded",
        case_id=case_id,
        file_name=video_file.filename,
        user=current_user.email,
        notes="Video file uploaded for analysis",
    )

    # Run video analysis
    try:
        report = analyze_video(
            str(video_path),
            case_dir=str(case_dir),
            file_key=file_key,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "video_upload.html",
            {
                "current_user": current_user,
                "error": f"Analysis failed: {str(e)}",
                "cases": [],
            },
            status_code=500,
        )

    log_audit_event(
        event_type="video_analysis_completed",
        case_id=case_id,
        file_name=video_file.filename,
        user=current_user.email,
        notes="Video forensic analysis completed",
        extra={
            "frames_analyzed": report.get("summary", {}).get("frames_analyzed", 0),
            "frames_flagged": report.get("summary", {}).get("frames_flagged", 0),
            "overall_assessment": report.get("summary", {}).get("overall_assessment", ""),
        },
    )

    return templates.TemplateResponse(
        request,
        "video_result.html",
        {
            "current_user": current_user,
            "case_id": case_id,
            "report": report,
        },
    )
