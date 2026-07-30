from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud.tuition.teaching_setup import get_teaching_setup
from app.db.session import get_db
from app.routes.tuition.teaching_setup import _ensure_access
from app.schemas.tuition.class_sessions import (
    ClassSessionListResponse,
    ClassSessionStartResponse,
    ClassSessionUpdate,
    TeachingSetupClassSessionCreate,
    TeachingSetupClassSessionListResponse,
    TeachingSetupClassSessionResponse,
    TeachingSetupClassSessionUpdate,
)
from app.schemas.users import UserRole
from app.services.tuition.class_sessions import (
    build_class_session_list_response,
    build_session_response,
    build_start_response,
    create_class_session_service,
    list_class_sessions_service,
    list_sessions_for_range,
    mark_class_session_not_done,
    start_live_class,
    update_class_session_service,
)
from app.utils.permission import require_roles

router = APIRouter(prefix="/tuition/teaching-setups", tags=["Tuition Teaching Setup Class Sessions"])


@router.post("/{teaching_setup_id}/class-sessions", response_model=TeachingSetupClassSessionResponse)
def create_class_session_endpoint(
    teaching_setup_id: str,
    payload: TeachingSetupClassSessionCreate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    teaching_setup = get_teaching_setup(db, teaching_setup_id)
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    session = create_class_session_service(db, current_user=current_user, teaching_setup=teaching_setup, payload=payload)
    return session


@router.get("/{teaching_setup_id}/class-sessions", response_model=ClassSessionListResponse)
def list_class_sessions_endpoint(
    teaching_setup_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    teaching_setup = get_teaching_setup(db, teaching_setup_id)
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, teaching_setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)

    if date_from is not None and date_to is not None:
        sessions = list_sessions_for_range(db, teaching_setup, date_from, date_to)
        return build_class_session_list_response(teaching_setup, sessions)

    sessions = list_class_sessions_service(db, teaching_setup=teaching_setup)
    return ClassSessionListResponse(
        teaching_setup_id=teaching_setup.id,
        sessions=[
            build_session_response(
                teaching_setup,
                session,
                session.session_date,
                datetime.now(timezone.utc),
            )
            for session in sessions
        ],
    )


@router.post("/{teaching_setup_id}/class-sessions/{class_date}/start", response_model=ClassSessionStartResponse)
def start_class_session_endpoint(
    teaching_setup_id: str,
    class_date: date,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    teaching_setup = get_teaching_setup(db, teaching_setup_id)
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, teaching_setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)

    session_row = start_live_class(db, teaching_setup, class_date, datetime.now(timezone.utc))
    response_payload = build_start_response(
        build_session_response(teaching_setup, session_row, class_date, datetime.now(timezone.utc)),
        message="Class session started.",
    )
    return response_payload


@router.patch("/{teaching_setup_id}/class-sessions/{class_date}", response_model=ClassSessionStartResponse)
def update_class_session_endpoint(
    teaching_setup_id: str,
    class_date: date,
    payload: ClassSessionUpdate,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    teaching_setup = get_teaching_setup(db, teaching_setup_id)
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, teaching_setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)

    session_row = mark_class_session_not_done(db, teaching_setup, class_date, payload)
    response_payload = build_start_response(
        build_session_response(teaching_setup, session_row, class_date, datetime.now(timezone.utc)),
        message="Class session updated.",
    )
    return response_payload


@router.put("/{teaching_setup_id}/class-sessions/{session_date}", response_model=TeachingSetupClassSessionResponse)
def update_class_session_legacy_endpoint(
    teaching_setup_id: str,
    session_date: date,
    payload: TeachingSetupClassSessionUpdate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    teaching_setup = get_teaching_setup(db, teaching_setup_id)
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    session = update_class_session_service(
        db,
        current_user=current_user,
        teaching_setup=teaching_setup,
        session_date=session_date,
        payload=payload,
    )
    return session
