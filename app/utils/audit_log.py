# app/utils/audit_log.py

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


BASE_DIR = Path(__file__).resolve().parents[2]
CASES_DIR = BASE_DIR / "cases"


def get_case_dir(case_id: str) -> Path:
    return CASES_DIR / case_id


def get_audit_log_path(case_id: str) -> Path:
    return get_case_dir(case_id) / "audit_log.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_case_dir(case_id: str) -> None:
    case_dir = get_case_dir(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)


def load_audit_log(case_id: str) -> List[Dict[str, Any]]:
    ensure_case_dir(case_id)
    audit_log_path = get_audit_log_path(case_id)

    if not audit_log_path.exists():
        return []

    try:
        with open(audit_log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError):
        return []


def save_audit_log(case_id: str, events: List[Dict[str, Any]]) -> None:
    ensure_case_dir(case_id)
    audit_log_path = get_audit_log_path(case_id)

    with open(audit_log_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)


def next_event_id(case_id: str) -> str:
    events = load_audit_log(case_id)
    return f"A-{len(events) + 1:04d}"


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
    event = {
        "event_id": next_event_id(case_id),
        "timestamp": utc_now_iso(),
        "case_id": case_id,
        "evidence_id": evidence_id,
        "event_type": event_type,
        "file_name": file_name,
        "sha256": sha256,
        "user": user,
        "notes": notes,
    }

    if extra:
        event["extra"] = extra

    return event


def append_audit_event(case_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
    events = load_audit_log(case_id)
    events.append(event)
    save_audit_log(case_id, events)
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