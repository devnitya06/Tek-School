from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.crud.tuition.teaching_setup import delete_teaching_setup, get_teaching_setup, list_teaching_setups, update_teaching_setup
from app.models.tuition.teaching_setup import TuitionTeachingSetup
from app.models.tuition_models import TuitionBatch, TuitionLessonPlan
from app.schemas.tuition.teaching_setup import (
    TeachingSetupCreate,
    TeachingSetupCreateResponse,
    TeachingSetupDetailResponse,
    TeachingSetupListResponse,
    TeachingSetupRatingCreate,
    TeachingSetupRatingResponse,
    TeachingSetupStatusUpdate,
    TeachingSetupSummaryResponse,
    TeachingSetupUpdate,
)
from app.schemas.users import UserRole
from app.services.tuition.teaching_setup import (
    create_teaching_setup_service,
    ensure_teacher_scope,
    get_tuition_setup_rating_summary,
    submit_teaching_setup_rating_service,
    update_teaching_setup_service,
)
from app.utils.permission import require_roles
from app.utils.tuition_helpers import resolve_lesson_plan_subject_name

router = APIRouter(prefix="/tuition/teaching-setups", tags=["Tuition Teaching Setups"])


def _serialize_teaching_setup(db: Session, setup: TuitionTeachingSetup, current_user=None) -> TeachingSetupSummaryResponse:
    lesson_plan = None
    batch = None
    rating_summary = get_tuition_setup_rating_summary(db, setup.id)
    if setup.lesson_plan_id:
        lesson_plan = db.query(TuitionLessonPlan).filter(TuitionLessonPlan.id == setup.lesson_plan_id, TuitionLessonPlan.is_deleted.is_(False)).first()
    if setup.batch_id:
        batch = db.query(TuitionBatch).filter(TuitionBatch.id == setup.batch_id, TuitionBatch.is_deleted.is_(False)).first()

    return TeachingSetupSummaryResponse(
        id=setup.id,
        lesson_plan_id=setup.lesson_plan_id,
        batch_id=setup.batch_id,
        lesson_plan_title=getattr(lesson_plan, "lesson_title", None),
        batch_name=getattr(batch, "batch_name", None),
        subject_name=resolve_lesson_plan_subject_name(db, lesson_plan, current_user),
        teaching_mode=setup.teaching_mode,
        monthly_tuition_fee=float(setup.monthly_tuition_fee or 0),
        monthly_tuition_discount=float(setup.monthly_tuition_discount or 0),
        final_tuition_fee=float(setup.final_tuition_fee or 0),
        premium_study_material_fee=float(setup.premium_study_material_fee or 0),
        premium_study_material_discount=float(setup.premium_study_material_discount or 0),
        final_premium_fee=float(setup.final_premium_fee or 0),
        joined_students_count=setup.joined_students_count,
        maximum_students=setup.maximum_students or 200,
        available_seats=setup.available_seats,
        average_rating=rating_summary["average_rating"],
        total_reviews=rating_summary["total_reviews"],
        status=setup.status,
        created_at=setup.created_at,
    )


def _serialize_teaching_setup_detail(db: Session, setup: TuitionTeachingSetup, current_user=None) -> TeachingSetupDetailResponse:
    summary = _serialize_teaching_setup(db, setup, current_user)
    return TeachingSetupDetailResponse(
        id=summary.id,
        lesson_plan_id=summary.lesson_plan_id,
        batch_id=summary.batch_id,
        lesson_plan_title=summary.lesson_plan_title,
        batch_name=summary.batch_name,
        subject_name=summary.subject_name,
        teaching_mode=summary.teaching_mode,
        batch_title=setup.batch_title,
        batch_start_date=setup.batch_start_date,
        batch_end_date=setup.batch_end_date,
        tuition_from_time=setup.tuition_from_time,
        tuition_to_time=setup.tuition_to_time,
        tuition_days=list(setup.tuition_days or []),
        languages=list(setup.languages or []),
        subjects=list(setup.subjects or []),
        material_update_days=list(setup.material_update_days or []),
        upload_from_time=setup.upload_from_time,
        upload_to_time=setup.upload_to_time,
        monthly_tuition_fee=summary.monthly_tuition_fee,
        monthly_tuition_discount=summary.monthly_tuition_discount,
        final_tuition_fee=summary.final_tuition_fee,
        premium_study_material_fee=summary.premium_study_material_fee,
        premium_study_material_discount=summary.premium_study_material_discount,
        final_premium_fee=summary.final_premium_fee,
        joined_students_count=summary.joined_students_count,
        maximum_students=summary.maximum_students,
        available_seats=summary.available_seats,
        average_rating=summary.average_rating,
        total_reviews=summary.total_reviews,
        meeting_provider=setup.meeting_provider,
        meeting_link=str(setup.meeting_link) if setup.meeting_link else None,
        online_teaching_ability=setup.online_teaching_ability,
        stable_internet_connection=setup.stable_internet_connection,
        camera_available=setup.camera_available,
        silent_place_without_background_noise=setup.silent_place_without_background_noise,
        laptop_desktop_pc=setup.laptop_desktop_pc,
        headphone_whiteboard=setup.headphone_whiteboard,
        status=summary.status,
        created_at=summary.created_at,
        updated_at=setup.updated_at,
    )


def _resolve_scope_ids(current_user, teacher_id: Optional[str], self_signed_teacher_id: Optional[int]):
    effective_teacher_id = teacher_id
    effective_self_signed_teacher_id = self_signed_teacher_id
    if getattr(current_user, "role", None) == UserRole.TEACHER and effective_teacher_id is None:
        effective_teacher_id = getattr(getattr(current_user, "teacher_profile", None), "id", None)
    if getattr(current_user, "role", None) == UserRole.SELF_SIGNED_TEACHER and effective_self_signed_teacher_id is None:
        effective_self_signed_teacher_id = getattr(getattr(current_user, "self_signed_teacher_profile", None), "id", None)
    return effective_teacher_id, effective_self_signed_teacher_id


def _ensure_access(current_user, setup: TuitionTeachingSetup, *, teacher_id: Optional[str], self_signed_teacher_id: Optional[int]):
    effective_teacher_id, effective_self_signed_teacher_id = _resolve_scope_ids(current_user, teacher_id, self_signed_teacher_id)
    if getattr(current_user, "role", None) in {UserRole.ADMIN, UserRole.SUPERADMIN}:
        return
    if getattr(setup, "created_by_user_id", None) == getattr(current_user, "id", None):
        return
    if not ensure_teacher_scope(current_user, teacher_id=effective_teacher_id, self_signed_teacher_id=effective_self_signed_teacher_id):
        raise HTTPException(status_code=403, detail="You can only access your own teaching setup")
    if setup.created_by_teacher_id and effective_teacher_id and setup.created_by_teacher_id != effective_teacher_id:
        raise HTTPException(status_code=403, detail="You can only access your own teaching setup")
    if setup.created_by_self_signed_teacher_id is not None and effective_self_signed_teacher_id is not None and setup.created_by_self_signed_teacher_id != effective_self_signed_teacher_id:
        raise HTTPException(status_code=403, detail="You can only access your own teaching setup")


@router.post("", response_model=TeachingSetupCreateResponse)
def create_teaching_setup_endpoint(
    payload: TeachingSetupCreate,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    setup = create_teaching_setup_service(
        db,
        current_user=current_user,
        payload=payload,
        teacher_id=teacher_id,
        self_signed_teacher_id=self_signed_teacher_id,
    )
    return TeachingSetupCreateResponse(message="Teaching setup created successfully.", teaching_setup_id=setup.id)


@router.get("/my", response_model=list[TeachingSetupSummaryResponse])
def my_teaching_setups(
    teaching_mode: Optional[str] = None,
    lesson_plan_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    effective_teacher_id, effective_self_signed_teacher_id = _resolve_scope_ids(current_user, teacher_id, self_signed_teacher_id)
    if getattr(current_user, "role", None) not in {UserRole.ADMIN, UserRole.SUPERADMIN}:
        if not ensure_teacher_scope(current_user, teacher_id=effective_teacher_id, self_signed_teacher_id=effective_self_signed_teacher_id):
            raise HTTPException(status_code=403, detail="You can only view your own teaching setups")
    items = list_teaching_setups(
        db,
        teacher_id=effective_teacher_id,
        self_signed_teacher_id=effective_self_signed_teacher_id,
        owner_user_id=getattr(current_user, "id", None),
        teaching_mode=teaching_mode,
        lesson_plan_id=lesson_plan_id,
        batch_id=batch_id,
        status=status,
        search=search,
        include_inactive=include_inactive,
    )
    return [_serialize_teaching_setup(db, item, current_user) for item in items]


@router.get("/{teaching_setup_id}", response_model=TeachingSetupDetailResponse)
def teaching_setup_detail(
    teaching_setup_id: str,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    setup = get_teaching_setup(db, teaching_setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)
    return _serialize_teaching_setup_detail(db, setup, current_user)


@router.post("/{teaching_setup_id}/ratings", response_model=TeachingSetupRatingResponse)
def submit_teaching_setup_rating_endpoint(
    teaching_setup_id: str,
    payload: TeachingSetupRatingCreate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
):
    setup = get_teaching_setup(db, teaching_setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")

    rating_row = submit_teaching_setup_rating_service(
        db,
        current_user=current_user,
        teaching_setup=setup,
        payload=payload,
    )
    rating_summary = get_tuition_setup_rating_summary(db, setup.id)
    return TeachingSetupRatingResponse(
        message="Rating submitted successfully.",
        average_rating=rating_summary["average_rating"],
        total_reviews=rating_summary["total_reviews"],
        your_rating=rating_row.rating,
    )


@router.put("/{teaching_setup_id}", response_model=TeachingSetupDetailResponse)
def update_teaching_setup_endpoint(
    teaching_setup_id: str,
    payload: TeachingSetupUpdate,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    setup = get_teaching_setup(db, teaching_setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)
    updated = update_teaching_setup_service(db, teaching_setup=setup, payload=payload)
    return _serialize_teaching_setup_detail(db, updated, current_user)


@router.delete("/{teaching_setup_id}", status_code=status.HTTP_200_OK)
def delete_teaching_setup_endpoint(
    teaching_setup_id: str,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    setup = get_teaching_setup(db, teaching_setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)
    delete_teaching_setup(db, setup)
    return {"message": "Teaching setup deleted successfully."}


@router.patch("/{teaching_setup_id}/status", response_model=TeachingSetupDetailResponse)
def change_teaching_setup_status(
    teaching_setup_id: str,
    payload: TeachingSetupStatusUpdate,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    setup = get_teaching_setup(db, teaching_setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")
    _ensure_access(current_user, setup, teacher_id=teacher_id, self_signed_teacher_id=self_signed_teacher_id)
    setup.status = payload.status.upper()
    update_teaching_setup(db, setup, payload={"status": setup.status})
    return _serialize_teaching_setup_detail(db, setup, current_user)
