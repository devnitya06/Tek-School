from typing import Optional

from pydantic import AnyUrl
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.tuition.teaching_setup import TuitionTeachingSetup


def get_teaching_setup(db: Session, teaching_setup_id: str):
    return (
        db.query(TuitionTeachingSetup)
        .filter(TuitionTeachingSetup.id == teaching_setup_id, TuitionTeachingSetup.is_deleted.is_(False))
        .first()
    )


def list_teaching_setups(
    db: Session,
    *,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    teaching_mode: Optional[str] = None,
    lesson_plan_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
):
    query = db.query(TuitionTeachingSetup).filter(TuitionTeachingSetup.is_deleted.is_(False))
    if not include_inactive:
        query = query.filter(TuitionTeachingSetup.status == "ACTIVE")
    if teacher_id:
        query = query.filter(TuitionTeachingSetup.created_by_teacher_id == teacher_id)
    if self_signed_teacher_id is not None:
        query = query.filter(TuitionTeachingSetup.created_by_self_signed_teacher_id == self_signed_teacher_id)
    if owner_user_id is not None:
        query = query.filter(TuitionTeachingSetup.created_by_user_id == owner_user_id)
    if teaching_mode:
        query = query.filter(TuitionTeachingSetup.teaching_mode == teaching_mode)
    if lesson_plan_id:
        query = query.filter(TuitionTeachingSetup.lesson_plan_id == lesson_plan_id)
    if batch_id:
        query = query.filter(TuitionTeachingSetup.batch_id == batch_id)
    if status:
        query = query.filter(TuitionTeachingSetup.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                TuitionTeachingSetup.batch_title.ilike(like),
                TuitionTeachingSetup.teaching_mode.ilike(like),
                TuitionTeachingSetup.status.ilike(like),
            )
        )
    return query.order_by(TuitionTeachingSetup.created_at.desc()).all()


def create_teaching_setup(
    db: Session,
    *,
    payload: dict,
    owner_user_id: Optional[int],
    owner_teacher_id: Optional[str],
    owner_self_signed_teacher_id: Optional[int],
):
    teacher_type_value = payload.get("teacher_type") or ("self_signed_teacher" if owner_self_signed_teacher_id is not None else "teacher")
    is_active_value = payload.get("is_active", True)

    model = TuitionTeachingSetup(
        lesson_plan_id=payload.get("lesson_plan_id"),
        batch_id=payload.get("batch_id"),
        teaching_mode=payload.get("teaching_mode") or "ONLINE_CLASS_AND_STUDY_MATERIALS",
        batch_title=payload.get("batch_title"),
        batch_start_date=payload.get("batch_start_date"),
        batch_end_date=payload.get("batch_end_date"),
        tuition_from_time=payload.get("tuition_from_time"),
        tuition_to_time=payload.get("tuition_to_time"),
        tuition_days=payload.get("tuition_days"),
        languages=payload.get("languages"),
        subjects=payload.get("subjects"),
        material_update_days=payload.get("material_update_days"),
        upload_from_time=payload.get("upload_from_time"),
        upload_to_time=payload.get("upload_to_time"),
        monthly_tuition_fee=payload.get("monthly_tuition_fee") or 0,
        monthly_tuition_discount=payload.get("monthly_tuition_discount") or 0,
        premium_study_material_fee=payload.get("premium_study_material_fee") or 0,
        premium_study_material_discount=payload.get("premium_study_material_discount") or 0,
        maximum_students=payload.get("maximum_students") or 200,
        teacher_type=teacher_type_value,
        is_active=is_active_value,
        meeting_provider=payload.get("meeting_provider"),
        meeting_link=str(payload.get("meeting_link")) if payload.get("meeting_link") is not None else None,
        online_teaching_ability=payload.get("online_teaching_ability"),
        stable_internet_connection=payload.get("stable_internet_connection"),
        camera_available=payload.get("camera_available"),
        silent_place_without_background_noise=payload.get("silent_place_without_background_noise"),
        laptop_desktop_pc=payload.get("laptop_desktop_pc"),
        headphone_whiteboard=payload.get("headphone_whiteboard"),
        status=payload.get("status") or "ACTIVE",
        created_by_user_id=owner_user_id,
        created_by_teacher_id=owner_teacher_id,
        created_by_self_signed_teacher_id=owner_self_signed_teacher_id,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def update_teaching_setup(db: Session, teaching_setup: TuitionTeachingSetup, *, payload: dict):
    for key, value in payload.items():
        if value is None:
            continue
        # psycopg2 cannot adapt Pydantic URL types — cast them to plain str
        if isinstance(value, AnyUrl):
            value = str(value)
        setattr(teaching_setup, key, value)
    db.commit()
    db.refresh(teaching_setup)
    return teaching_setup


def delete_teaching_setup(db: Session, teaching_setup: TuitionTeachingSetup):
    teaching_setup.is_deleted = True
    teaching_setup.status = "INACTIVE"
    teaching_setup.deleted_at = teaching_setup.updated_at
    db.commit()
    return teaching_setup
