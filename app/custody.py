from app.db import SessionLocal
from app.models import CustodyLog


def log_custody(
    case_id: str,
    action: str,
    user_id: int = None,
    user_email: str = None,
    evidence_id: str = None,
    detail: str = None,
    ip_address: str = None,
):
    db = SessionLocal()
    try:
        entry = CustodyLog(
            case_id=case_id,
            evidence_id=evidence_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"CustodyLog error: {e}")
    finally:
        db.close()
