import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db import SessionLocal
from app.models import CustodyLog


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_chain_hash(prev_chain_hash: Optional[str], event: Dict[str, Any]) -> str:
    """
    SHA-256( prev_chain_hash + serialized event content ).
    If this is the first row, prev_chain_hash is treated as an empty string.
    Serialization is deterministic: sorted keys, no whitespace.
    """
    content_fields = {
        "event_type": event.get("event_type"),
        "case_id":    event.get("case_id"),
        "evidence_id": event.get("evidence_id"),
        "user":       event.get("user"),
        "ip_address": event.get("ip_address"),
        "notes":      event.get("notes"),
    }
    serialized = json.dumps(content_fields, sort_keys=True, separators=(",", ":"))
    raw = (prev_chain_hash or "") + serialized
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_audit_event(
    event_type: str,
    case_id: str,
    evidence_id: Optional[str] = None,
    file_name: Optional[str] = None,
    sha256: Optional[str] = None,
    user: str = "system",
    ip_address: Optional[str] = None,
    notes: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "case_id":    case_id,
        "evidence_id": evidence_id,
        "file_name":  file_name,
        "sha256":     sha256,
        "user":       user,
        "ip_address": ip_address,
        "notes":      notes,
        "extra":      extra,
     }


def append_audit_event(
    case_id: str,
    event: Dict[str, Any],
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes the event to the CustodyLog table.
    Computes chain_hash = SHA-256(prev_row.chain_hash + serialized event).
    ip_address can be passed here directly (overrides whatever is in the event dict).
    """
    # Allow ip_address to be passed at call-site or pre-set on the event dict
    resolved_ip = ip_address or event.get("ip_address")
    event["ip_address"] = resolved_ip

    db = SessionLocal()
    try:
        # Fetch the most recent chain_hash for this case
        last = (
            db.query(CustodyLog.chain_hash)
            .filter(CustodyLog.case_id == case_id)
            .order_by(CustodyLog.created_at.desc())
            .first()
        )
        prev_hash = last[0] if last else None
        new_chain_hash = _compute_chain_hash(prev_hash, event)

        entry = CustodyLog(
            case_id=case_id,
            evidence_id=event.get("evidence_id"),
            user_email=event.get("user"),
            action=event.get("event_type"),
            detail=event.get("notes") or event.get("file_name"),
            ip_address=resolved_ip,
            chain_hash=new_chain_hash,
        )
        db.add(entry)
        db.commit()

        event["chain_hash"] = new_chain_hash

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
    ip_address: Optional[str] = None,
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
        ip_address=ip_address,
        notes=notes,
        extra=extra,
    )
    return append_audit_event(case_id, event, ip_address=ip_address)


def load_audit_log(
    case_id: str,
    ip_address: Optional[str] = None,   # unused here, kept for signature consistency
) -> List[Dict[str, Any]]:
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
                "event_type":  e.action,
                "case_id":     e.case_id,
                "evidence_id": e.evidence_id,
                "user":        e.user_email,
                "ip_address":  e.ip_address,
                "notes":       e.detail,
                "chain_hash":  e.chain_hash,
             }
            for e in entries
        ]
    except Exception as ex:
        print(f"CustodyLog load error: {ex}")
        return []
    finally:
        db.close()


def verify_chain(case_id: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Walks every row for this case in chronological order and recomputes each
    chain_hash from scratch.  Returns:

        (True, None, None)                 — chain is intact
        (False, broken_row_id, detail_msg) — first broken link found

    The Custody Record's Section 7 should call this at generation time and
    surface the result as the chain integrity statement.
    """
    db = SessionLocal()
    try:
        entries = (
            db.query(CustodyLog)
            .filter(CustodyLog.case_id == case_id)
            .order_by(CustodyLog.created_at.asc())
            .all()
        )

        prev_hash: Optional[str] = None

        for entry in entries:
            event_snapshot = {
                "event_type":  entry.action,
                "case_id":     entry.case_id,
                "evidence_id": entry.evidence_id,
                "file_name":   None,
                "sha256":      None,
                "user":        entry.user_email,
                "ip_address":  entry.ip_address,
                "notes":       entry.detail,
                "extra":       None,
           }
      
            expected = _compute_chain_hash(prev_hash, event_snapshot)

            if entry.chain_hash != expected:
                msg = (
                    f"Chain break at row id={entry.id} "
                    f"(action={entry.action!r}, created_at={entry.created_at}). "
                    f"Stored hash {entry.chain_hash!r} does not match "
                    f"recomputed hash {expected!r}."
                )
                return False, entry.id, msg

            prev_hash = entry.chain_hash

        return True, None, None

    except Exception as ex:
        print(f"verify_chain error: {ex}")
        return False, None, f"Verification error: {ex}"
    finally:
        db.close()