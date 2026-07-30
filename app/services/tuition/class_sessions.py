from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.tuition.class_sessions import list_class_sessions as crud_list_class_sessions
from app.crud.tuition.class_sessions import update_class_session as crud_update_class_session
from app.crud.tuition.class_sessions import upsert_class_session as crud_upsert_class_session
from app.models.tuition.class_sessions import TuitionTeachingSetupClassSession
from app.models.tuition.teaching_setup import TuitionTeachingSetup
from app.schemas.tuition.class_sessions import (
    ClassSessionListResponse,
    ClassSessionResponse,
    ClassSessionStartResponse,
    ClassSessionStatus,
    ClassSessionUpdate,
    TeachingSetupClassSessionCreate,
    TeachingSetupClassSessionUpdate,
)
from app.schemas.users import UserRole


def _ensure_owner_access(current_user, teaching_setup: TuitionTeachingSetup):
    if getattr(current_user, "role", None) in {UserRole.ADMIN, UserRole.SUPERADMIN}:
        return
    if getattr(teaching_setup, "created_by_user_id", None) == getattr(current_user, "id", None):
        return
    if getattr(current_user, "role", None) == UserRole.TEACHER and getattr(teaching_setup, "created_by_teacher_id", None) and getattr(getattr(current_user, "teacher_profile", None), "id", None) == teaching_setup.created_by_teacher_id:
        return
    if getattr(current_user, "role", None) == UserRole.SELF_SIGNED_TEACHER and getattr(teaching_setup, "created_by_self_signed_teacher_id", None) is not None and getattr(getattr(current_user, "self_signed_teacher_profile", None), "id", None) == teaching_setup.created_by_self_signed_teacher_id:
        return
    raise HTTPException(status_code=403, detail="You can only access your own teaching setup")


def create_class_session_service(
    db: Session,
    *,
    current_user,
    teaching_setup: TuitionTeachingSetup,
    payload: TeachingSetupClassSessionCreate,
):
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_owner_access(current_user, teaching_setup)

    session_date = payload.session_date
    now = datetime.now(timezone.utc)
    return crud_upsert_class_session(
        db,
        teaching_setup_id=teaching_setup.id,
        session_date=session_date,
        status="IN_PROGRESS",
        notes=payload.notes,
        started_at=now,
        completed_at=None,
    )


def list_class_sessions_service(db: Session, *, teaching_setup: TuitionTeachingSetup, date_from: date | None = None, date_to: date | None = None):
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    return crud_list_class_sessions(db, teaching_setup_id=teaching_setup.id, date_from=date_from, date_to=date_to)


def update_class_session_service(
    db: Session,
    *,
    current_user,
    teaching_setup: TuitionTeachingSetup,
    session_date,
    payload: TeachingSetupClassSessionUpdate,
):
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_owner_access(current_user, teaching_setup)

    session = (
        db.query(TuitionTeachingSetupClassSession)
        .filter(
            TuitionTeachingSetupClassSession.teaching_setup_id == teaching_setup.id,
            TuitionTeachingSetupClassSession.session_date == session_date,
            TuitionTeachingSetupClassSession.is_deleted.is_(False),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Class session not found")

    payload_dict = payload.model_dump(exclude_unset=True)
    if payload_dict.get("status") == "COMPLETED":
        payload_dict["completed_at"] = datetime.now(timezone.utc)
    elif payload_dict.get("status") in {"IN_PROGRESS", "PENDING"}:
        payload_dict["completed_at"] = None

    return crud_update_class_session(db, session, payload=payload_dict)


def _normalize_weekday(class_date: date) -> str:
    return class_date.strftime("%a").upper()[:3]


def _get_window_bounds(class_date: date, start_time: time | None) -> tuple[datetime, datetime]:
    if start_time is None:
        raise HTTPException(status_code=400, detail="tuition_from_time is required")
    start_dt = datetime.combine(class_date, start_time)
    window_start = start_dt - timedelta(minutes=15)
    window_end = start_dt + timedelta(minutes=30)
    return window_start, window_end


def build_session_response(teaching_setup: TuitionTeachingSetup, session_row: TuitionTeachingSetupClassSession | None, class_date: date, now: datetime) -> ClassSessionResponse:
    weekday = _normalize_weekday(class_date)
    scheduled_start_time = teaching_setup.tuition_from_time or time(0, 0)
    scheduled_end_time = teaching_setup.tuition_to_time or time(0, 0)
    status_value = getattr(session_row, "status", None) or ClassSessionStatus.NOT_STARTED.value
    if isinstance(status_value, ClassSessionStatus):
        status = status_value
    else:
        try:
            status = ClassSessionStatus(status_value)
        except ValueError:
            status = ClassSessionStatus.NOT_STARTED

    is_clickable = False
    if class_date == now.date() and weekday in (teaching_setup.tuition_days or []) and session_row is None:
        window_start, window_end = _get_window_bounds(class_date, scheduled_start_time)
        is_clickable = window_start <= now <= window_end

    return ClassSessionResponse(
        teaching_setup_id=teaching_setup.id,
        class_date=class_date,
        weekday=weekday,
        scheduled_start_time=scheduled_start_time,
        scheduled_end_time=scheduled_end_time,
        status=status,
        reason=getattr(session_row, "reason", None) if session_row else None,
        started_at=getattr(session_row, "started_at", None) if session_row else None,
        is_clickable=is_clickable,
        meeting_link=teaching_setup.meeting_link,
    )


def start_live_class(db: Session, teaching_setup: TuitionTeachingSetup, class_date: date, now: datetime):
    weekday = _normalize_weekday(class_date)
    if weekday not in (teaching_setup.tuition_days or []):
        raise HTTPException(status_code=400, detail=f"{class_date} is not a scheduled tuition day for this batch.")

    scheduled_start_time = teaching_setup.tuition_from_time or time(0, 0)
    window_start, window_end = _get_window_bounds(class_date, scheduled_start_time)
    if not (window_start <= now <= window_end):
        raise HTTPException(status_code=400, detail=f"Class can only be started between {window_start} and {window_end} on {class_date}.")

    return crud_upsert_class_session(
        db,
        teaching_setup_id=teaching_setup.id,
        session_date=class_date,
        status=ClassSessionStatus.LIVE.value,
        started_at=now,
        completed_at=None,
    )


def mark_class_session_not_done(db: Session, teaching_setup: TuitionTeachingSetup, class_date: date, payload: ClassSessionUpdate):
    session = (
        db.query(TuitionTeachingSetupClassSession)
        .filter(
            TuitionTeachingSetupClassSession.teaching_setup_id == teaching_setup.id,
            TuitionTeachingSetupClassSession.session_date == class_date,
            TuitionTeachingSetupClassSession.is_deleted.is_(False),
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"Class for {class_date} hasn't started, nothing to update.")

    if payload.status == ClassSessionStatus.NOT_DONE and not payload.reason:
        raise HTTPException(status_code=422, detail="reason is required when status is NOT_DONE.")

    payload_dict = {
        "status": payload.status.value,
        "reason": payload.reason,
        "completed_at": datetime.now(timezone.utc) if payload.status in {ClassSessionStatus.DONE, ClassSessionStatus.NOT_DONE} else None,
    }
    return crud_update_class_session(db, session, payload=payload_dict)


def list_sessions_for_range(db: Session, teaching_setup: TuitionTeachingSetup, date_from: date, date_to: date) -> list[ClassSessionResponse]:
    sessions = {session.session_date: session for session in crud_list_class_sessions(db, teaching_setup_id=teaching_setup.id, date_from=date_from, date_to=date_to)}
    now = datetime.now(timezone.utc)
    results = []
    current_date = date_from
    while current_date <= date_to:
        if _normalize_weekday(current_date) in (teaching_setup.tuition_days or []):
            results.append(build_session_response(teaching_setup, sessions.get(current_date), current_date, now))
        current_date += timedelta(days=1)
    return results


def build_class_session_list_response(teaching_setup: TuitionTeachingSetup, sessions: list[ClassSessionResponse]) -> ClassSessionListResponse:
    return ClassSessionListResponse(teaching_setup_id=teaching_setup.id, sessions=sessions)


def build_start_response(session: ClassSessionResponse, message: str = "Class session started.") -> ClassSessionStartResponse:
    return ClassSessionStartResponse(message=message, session=session)
