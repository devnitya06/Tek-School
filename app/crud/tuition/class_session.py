from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tuition.class_session import TuitionClassSession


def get_class_session(db: Session, teaching_setup_id: str, class_date: date) -> Optional[TuitionClassSession]:
    return (
        db.query(TuitionClassSession)
        .filter(
            TuitionClassSession.teaching_setup_id == teaching_setup_id,
            TuitionClassSession.class_date == class_date,
        )
        .first()
    )


def list_class_sessions(db: Session, teaching_setup_id: str, date_from: date, date_to: date) -> list[TuitionClassSession]:
    return (
        db.query(TuitionClassSession)
        .filter(
            TuitionClassSession.teaching_setup_id == teaching_setup_id,
            TuitionClassSession.class_date >= date_from,
            TuitionClassSession.class_date <= date_to,
        )
        .order_by(TuitionClassSession.class_date.asc())
        .all()
    )


def upsert_class_session_start(db: Session, teaching_setup_id: str, class_date: date) -> TuitionClassSession:
    session = get_class_session(db, teaching_setup_id, class_date)
    if session is not None:
        return session

    now = datetime.now(timezone.utc)
    session = TuitionClassSession(
        teaching_setup_id=teaching_setup_id,
        class_date=class_date,
        status="LIVE",
        started_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def update_class_session_status(db: Session, session: TuitionClassSession, status: str, reason: Optional[str] = None) -> TuitionClassSession:
    session.status = status
    if reason is not None:
        session.reason = reason
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session
