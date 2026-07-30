from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.tuition.class_session import (
    get_class_session,
    list_class_sessions,
    update_class_session_status,
    upsert_class_session_start,
)
from app.models.tuition.teaching_setup import TuitionTeachingSetup
from app.schemas.tuition.class_session import ClassSessionResponse, ClassSessionStatus, ClassSessionUpdate


def _normalize_weekday(day: date) -> str:
    return day.strftime("%a").upper()[:3]


def _get_window_bounds(class_date: date, start_time: Optional[time], now: datetime) -> tuple[datetime, datetime]:
    if start_time is None:
        raise HTTPException(status_code=400, detail="tuition_from_time is required")
    start_dt = datetime.combine(class_date, start_time)
    window_start = start_dt - timedelta(minutes=15)
    window_end = start_dt + timedelta(minutes=30)
    return window_start, window_end


def build_session_response(setup: TuitionTeachingSetup, session_row, class_date: date, now: datetime) -> ClassSessionResponse:
    weekday = _normalize_weekday(class_date)
    scheduled_start_time = setup.tuition_from_time or time(0, 0)
    scheduled_end_time = setup.tuition_to_time or time(0, 0)
    status = session_row.status if session_row is not None else ClassSessionStatus.NOT_STARTED.value
    session_exists = session_row is not None

    is_clickable = False
    if class_date == now.date() and weekday in (setup.tuition_days or []):
        if not session_exists:
            window_start, window_end = _get_window_bounds(class_date, scheduled_start_time, now)
            is_clickable = window_start <= now <= window_end

    return ClassSessionResponse(
        teaching_setup_id=setup.id,
        class_date=class_date,
        weekday=weekday,
        scheduled_start_time=scheduled_start_time,
        scheduled_end_time=scheduled_end_time,
        status=ClassSessionStatus(status),
        reason=getattr(session_row, "reason", None) if session_row is not None else None,
        started_at=getattr(session_row, "started_at", None) if session_row is not None else None,
        is_clickable=is_clickable,
        meeting_link=setup.meeting_link,
    )


def start_live_class(db: Session, setup: TuitionTeachingSetup, class_date: date, now: datetime):
    weekday = _normalize_weekday(class_date)
    if weekday not in (setup.tuition_days or []):
        raise HTTPException(status_code=400, detail=f"{class_date} is not a scheduled tuition day for this batch.")

    scheduled_start_time = setup.tuition_from_time or time(0, 0)
    window_start, window_end = _get_window_bounds(class_date, scheduled_start_time, now)
    if not (window_start <= now <= window_end):
        raise HTTPException(status_code=400, detail=f"Class can only be started between {window_start} and {window_end} on {class_date}.")

    return upsert_class_session_start(db, setup.id, class_date)


def mark_class_session_not_done(db: Session, setup: TuitionTeachingSetup, class_date: date, payload: ClassSessionUpdate):
    session = get_class_session(db, setup.id, class_date)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Class for {class_date} hasn't started, nothing to update.")

    if payload.status == ClassSessionStatus.NOT_DONE and not payload.reason:
        raise HTTPException(status_code=422, detail="reason is required when status is NOT_DONE.")

    return update_class_session_status(db, session, payload.status.value, payload.reason)


def list_sessions_for_range(db: Session, setup: TuitionTeachingSetup, date_from: date, date_to: date):
    sessions = {item.class_date: item for item in list_class_sessions(db, setup.id, date_from, date_to)}
    results = []
    current_date = date_from
    while current_date <= date_to:
        if _normalize_weekday(current_date) in (setup.tuition_days or []):
            session_row = sessions.get(current_date)
            results.append(build_session_response(setup, session_row, current_date, datetime.now(timezone.utc)))
        current_date += timedelta(days=1)
    return results
