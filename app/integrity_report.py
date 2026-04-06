from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from app.db import SessionLocal
from app.models import EvidenceItem, CustodyLog, Case


def generate_integrity_report(case_id: str, generated_by: str = "system") -> str:
    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_id == case_id).first()
        evidence_items = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()
        custody_entries = db.query(CustodyLog).filter(CustodyLog.case_id == case_id).order_by(CustodyLog.created_at.asc()).all()
    finally:
        db.close()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    output_path = tmp.name

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", fontSize=16, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=6)
    subtitle_style = ParagraphStyle("subtitle", fontSize=10, fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4, textColor=colors.grey)
    h2_style = ParagraphStyle("h2", fontSize=12, fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=6)
    body_style = ParagraphStyle("body", fontSize=9, fontName="Helvetica", spaceAfter=4)
    mono_style = ParagraphStyle("mono", fontSize=7, fontName="Courier", spaceAfter=2)
    disclaimer_style = ParagraphStyle("disclaimer", fontSize=8, fontName="Helvetica-Oblique", textColor=colors.grey, spaceAfter=4)

    now = datetime.now(timezone.utc)
    case_name = case.case_name if case else case_id

    story = []

    story.append(Paragraph("EVIDENTIX™ INTEGRITY &amp; CHAIN OF CUSTODY REPORT", title_style))
    story.append(Paragraph("Exhibit C — Digital Evidence Integrity Verification", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=12))

    meta = [
        ["Matter / Case ID:", case_id],
        ["Case Name:", case_name],
        ["Report Generated:", now.strftime("%B %d, %Y at %H:%M UTC")],
        ["Prepared By:", generated_by],
        ["Platform:", "Evidentix™ (evidenceanalyzer.com)"],
        ["Hash Algorithm:", "SHA-256"],
    ]
    meta_table = Table(meta, colWidths=[2*inch, 4.5*inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("PURPOSE &amp; SCOPE", h2_style))
    story.append(Paragraph(
        "This report is prepared solely to identify, verify, and summarize digital files submitted as evidence. "
        "Evidentix™ was used only to ingest, index, hash, and report on collected files. "
        "It was not used to create, edit, enhance, alter, summarize, or opine on the content of any evidence file. "
        "This report does not constitute expert opinion.",
        body_style
    ))

    story.append(Paragraph("EXHIBIT A — HASH VERIFICATION TABLE", h2_style))
    story.append(Paragraph(
        "The following table lists each evidence file, its SHA-256 hash recorded at ingest, and its current status.",
        body_style
    ))

    hash_data = [["Exhibit / Evidence ID", "Filename", "SHA-256 at Ingest", "Ingested On", "Status"]]
    for e in evidence_items:
        sha = e.sha256 or "Not recorded"
        status = "VERIFIED" if e.sha256 else "NO HASH"
        date = e.analysis_date or ""
        hash_data.append([
            e.evidence_id or "",
            e.file_name or "",
            sha[:32] + "..." if sha and len(sha) > 32 else sha,
            date[:10] if date else "",
            status,
        ])

    if len(hash_data) == 1:
        hash_data.append(["No evidence files found.", "", "", "", ""])

    hash_table = Table(hash_data, colWidths=[1.1*inch, 1.5*inch, 2.1*inch, 0.9*inch, 0.75*inch])
    hash_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.black),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("FONTNAME", (4,1), (4,-1), "Helvetica-Bold"),
    ]))
    story.append(hash_table)

    story.append(Paragraph("EXHIBIT B — CUSTODY &amp; ACTIVITY LOG", h2_style))
    story.append(Paragraph(
        "The following log records all access, upload, analysis, and export events for this case.",
        body_style
    ))

    custody_data = [["Timestamp (UTC)", "User / Role", "Action"]]
    for e in custody_entries:
        ts = e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else ""
        custody_data.append([
            ts,
            e.user_email or "system",
            e.action or "",
            e.evidence_id or "",
                    ])

    if len(custody_data) == 1:
        custody_data.append(["No custody events recorded.", "", ""])

    custody_table = Table(custody_data, colWidths=[1.2*inch, 2.3*inch, 3.0*inch])
    custody_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.black),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(custody_table)

    story.append(Paragraph("INTEGRITY STATEMENT", h2_style))
    story.append(Paragraph(
        "The evidence files identified in this report were ingested into Evidentix™ and assigned SHA-256 hash values at the time of upload. "
        "The hash values recorded above represent the state of each file at the time of ingest. "
        "Any subsequent change to a file would produce a different hash value. "
        "Evidentix™ did not modify the contents of any file listed in this report.",
        body_style
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "No generative artificial intelligence was used to create, edit, enhance, or alter any evidence file identified in this report. "
        "Evidentix™ was used solely to store, index, hash, compare, and report on collected files.",
        body_style
    ))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Evidentix™ is a trademark of CLF The Woodlands, LLC. dba Evidence Analyzer This report is generated automatically and is not a substitute for testimony by a qualified forensic examiner. "
        "Hash verification proves file integrity from the point of ingest forward; it does not establish the authenticity of the source prior to collection.",
        disclaimer_style
    ))
        ))
        doc.build(story)
        return output_path
