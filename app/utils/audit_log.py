import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.db import SessionLocal
from app.models import CustodyLog


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_audit_event(
    event_type: str,
    case_id: str,
    evidence_id: Optional[str] = None,
    file_name: Optional[str] = None,
    sha256: Optional[str] = None,
    user: str = "system",
    notes: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "case_id": case_id,
        "evidence_id": evidence_id,
        "file_name": file_name,
        "sha256": sha256,
        "user": user,
        "notes": notes,
        "extra": extra,
        "timestamp": utc_now_iso(),
    }


def append_audit_event(case_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        entry = CustodyLog(
            case_id=case_id,
            evidence_id=event.get("evidence_id"),
            user_email=event.get("user"),
            action=event.get("event_type"),
            detail=event.get("notes") or event.get("file_name"),
            ip_address=None,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"CustodyLog DB error: {e}")
    finally:
        db.close()
    return event


def log_audit_event(
    event_type: str,
    case_id: str,
    evidence_id: Optional[str] = None,
    file_name: Optional[str] = None,
    sha256: Optional[str] = None,
    user: str = "system",
    notes: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event = create_audit_event(
        event_type=event_type,
        case_id=case_id,
        evidence_id=evidence_id,
        file_name=file_name,
        sha256=sha256,
        user=user,
        notes=notes,
        extra=extra,
    )
    return append_audit_event(case_id, event)


def load_audit_log(case_id: str) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        entries = (
            db.query(CustodyLog)
            .filter(CustodyLog.case_id == case_id)
            .order_by(CustodyLog.created_at.asc())
            .all()
        )
        return [
            {
                "event_type": e.action,
                "case_id": e.case_id,
                "evidence_id": e.evidence_id,
                "user": e.user_email,
                "notes": e.detail,
                "timestamp": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]
    except Exception as ex:
        print(f"CustodyLog load error: {ex}")
        return []
    finally:
        db.close()
