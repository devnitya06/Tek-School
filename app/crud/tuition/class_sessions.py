from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tuition.class_sessions import TuitionTeachingSetupClassSession


def get_class_session(db: Session, *, teaching_setup_id: str, session_date: date):
    return (
        db.query(TuitionTeachingSetupClassSession)
        .filter(
            TuitionTeachingSetupClassSession.teaching_setup_id == teaching_setup_id,
            TuitionTeachingSetupClassSession.session_date == session_date,
            TuitionTeachingSetupClassSession.is_deleted.is_(False),
        )
        .first()
    )


def list_class_sessions(db: Session, *, teaching_setup_id: str, date_from: Optional[date] = None, date_to: Optional[date] = None):
    query = (
        db.query(TuitionTeachingSetupClassSession)
        .filter(
            TuitionTeachingSetupClassSession.teaching_setup_id == teaching_setup_id,
            TuitionTeachingSetupClassSession.is_deleted.is_(False),
        )
    )
    if date_from is not None:
        query = query.filter(TuitionTeachingSetupClassSession.session_date >= date_from)
    if date_to is not None:
        query = query.filter(TuitionTeachingSetupClassSession.session_date <= date_to)
    return query.order_by(TuitionTeachingSetupClassSession.session_date.asc()).all()


def upsert_class_session(
    db: Session,
    *,
    teaching_setup_id: str,
    session_date: date,
    status: str,
    notes: Optional[str] = None,
    started_at=None,
    completed_at=None,
    reason: Optional[str] = None,
):
    session = get_class_session(db, teaching_setup_id=teaching_setup_id, session_date=session_date)
    if session is None:
        session = TuitionTeachingSetupClassSession(
            teaching_setup_id=teaching_setup_id,
            session_date=session_date,
            status=status,
            notes=notes,
            reason=reason,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(session)
    else:
        if status is not None:
            session.status = status
        if notes is not None:
            session.notes = notes
        if reason is not None:
            session.reason = reason
        if started_at is not None and session.started_at is None:
            session.started_at = started_at
        if completed_at is not None:
            session.completed_at = completed_at
    db.commit()
    db.refresh(session)
    return session


def update_class_session(db: Session, session: TuitionTeachingSetupClassSession, *, payload: dict):
    for key, value in payload.items():
        if value is None:
            continue
        setattr(session, key, value)
    db.commit()
    db.refresh(session)
    return session


def delete_class_session(db: Session, session: TuitionTeachingSetupClassSession):
    session.is_deleted = True
    session.deleted_at = session.updated_at
    db.commit()
    return session
