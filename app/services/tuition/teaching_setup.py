from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.tuition.teaching_setup import create_teaching_setup as crud_create_teaching_setup
from app.crud.tuition.teaching_setup import update_teaching_setup as crud_update_teaching_setup
from app.db.session import ensure_tuition_teaching_setup_schema
from app.models.tuition.teaching_setup import TeachingMode, TeachingSetupStatus, TuitionTeachingSetup, TuitionTeachingSetupRating
from app.models.tuition_models import TuitionBatch, TuitionLessonPlan, TuitionLessonPlanBatch
from app.schemas.tuition.teaching_setup import TeachingSetupCreate, TeachingSetupRatingCreate, TeachingSetupUpdate
from app.schemas.users import UserRole


def _safe_get_attribute(obj, attr_name):
    try:
        return getattr(obj, attr_name, None)
    except Exception:
        return None


def _ensure_teaching_setup_table():
    try:
        ensure_tuition_teaching_setup_schema()
    except Exception:
        return


def _validate_payload(
    db: Session,
    payload: dict,
    *,
    owner_user_id: Optional[int] = None,
    owner_teacher_id: Optional[str] = None,
    owner_self_signed_teacher_id: Optional[int] = None,
    existing_setup_id: Optional[str] = None,
):
    _ensure_teaching_setup_table()
    teaching_mode = (payload.get("teaching_mode") or "").strip()
    if teaching_mode not in {TeachingMode.ONLINE_CLASS_AND_STUDY_MATERIALS.value, TeachingMode.STUDY_MATERIALS_ONLY.value}:
        raise HTTPException(status_code=400, detail="teaching_mode must be ONLINE_CLASS_AND_STUDY_MATERIALS or STUDY_MATERIALS_ONLY")

    lesson_plan_id = payload.get("lesson_plan_id")
    if not lesson_plan_id:
        raise HTTPException(status_code=400, detail="lesson_plan_id is required")

    lesson_plan = (
        db.query(TuitionLessonPlan)
        .filter(TuitionLessonPlan.id == lesson_plan_id, TuitionLessonPlan.is_deleted.is_(False))
        .first()
    )
    if not lesson_plan:
        raise HTTPException(status_code=404, detail="Lesson plan not found")
    if str(getattr(lesson_plan, "status", "")).upper() != "ACTIVE":
        raise HTTPException(status_code=400, detail="Lesson plan must be active")

    if existing_setup_id:
        batch_id = payload.get("batch_id")
        if teaching_mode == TeachingMode.ONLINE_CLASS_AND_STUDY_MATERIALS.value and batch_id:
            batch = db.query(TuitionBatch).filter(TuitionBatch.id == batch_id, TuitionBatch.is_deleted.is_(False)).first()
            if not batch:
                raise HTTPException(status_code=404, detail="Batch not found")
            mapping = (
                db.query(TuitionLessonPlanBatch)
                .filter(TuitionLessonPlanBatch.lesson_plan_id == lesson_plan_id, TuitionLessonPlanBatch.batch_id == batch_id)
                .first()
            )
            if not mapping:
                raise HTTPException(status_code=400, detail="Batch does not belong to the selected lesson plan")
        if payload.get("meeting_link"):
            parsed = urlparse(str(payload.get("meeting_link")))
            if not parsed.scheme or not parsed.netloc:
                raise HTTPException(status_code=400, detail="meeting_link must be a valid URL")
        return

    if teaching_mode == TeachingMode.ONLINE_CLASS_AND_STUDY_MATERIALS.value:
        batch_id = payload.get("batch_id")
        if not batch_id:
            raise HTTPException(status_code=400, detail="batch_id is required for ONLINE_CLASS_AND_STUDY_MATERIALS")
        batch = db.query(TuitionBatch).filter(TuitionBatch.id == batch_id, TuitionBatch.is_deleted.is_(False)).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        mapping = (
            db.query(TuitionLessonPlanBatch)
            .filter(TuitionLessonPlanBatch.lesson_plan_id == lesson_plan_id, TuitionLessonPlanBatch.batch_id == batch_id)
            .first()
        )
        if not mapping:
            raise HTTPException(status_code=400, detail="Batch does not belong to the selected lesson plan")
        if not payload.get("batch_title"):
            raise HTTPException(status_code=400, detail="batch_title is required")
        if not payload.get("batch_start_date") or not payload.get("batch_end_date"):
            raise HTTPException(status_code=400, detail="batch_start_date and batch_end_date are required")
        if payload.get("batch_end_date") <= payload.get("batch_start_date"):
            raise HTTPException(status_code=400, detail="batch_end_date must be greater than batch_start_date")
        if not payload.get("tuition_from_time") or not payload.get("tuition_to_time"):
            raise HTTPException(status_code=400, detail="tuition_from_time and tuition_to_time are required")
        if payload.get("tuition_from_time") >= payload.get("tuition_to_time"):
            raise HTTPException(status_code=400, detail="tuition_from_time must be less than tuition_to_time")
        if not payload.get("tuition_days"):
            raise HTTPException(status_code=400, detail="tuition_days must contain at least one day")
        if not payload.get("languages"):
            raise HTTPException(status_code=400, detail="languages cannot be empty")
        if payload.get("monthly_tuition_fee") is None:
            raise HTTPException(status_code=400, detail="monthly_tuition_fee is required")
        if payload.get("monthly_tuition_discount") is not None and payload.get("monthly_tuition_fee") is not None and payload.get("monthly_tuition_discount") > payload.get("monthly_tuition_fee"):
            raise HTTPException(status_code=400, detail="monthly_tuition_discount cannot exceed monthly_tuition_fee")
        if payload.get("premium_study_material_discount") is not None and payload.get("premium_study_material_fee") is not None and payload.get("premium_study_material_discount") > payload.get("premium_study_material_fee"):
            raise HTTPException(status_code=400, detail="premium_study_material_discount cannot exceed premium_study_material_fee")
        if payload.get("meeting_link"):
            parsed = urlparse(str(payload.get("meeting_link")))
            if not parsed.scheme or not parsed.netloc:
                raise HTTPException(status_code=400, detail="meeting_link must be a valid URL")
    else:
        if not payload.get("subjects"):
            raise HTTPException(status_code=400, detail="subjects must contain at least one item")
        if not payload.get("material_update_days") or len(payload.get("material_update_days") or []) < 4:
            raise HTTPException(status_code=400, detail="material_update_days must contain at least 4 days")
        if not payload.get("languages"):
            raise HTTPException(status_code=400, detail="languages cannot be empty")
        if not payload.get("upload_from_time") or not payload.get("upload_to_time"):
            raise HTTPException(status_code=400, detail="upload_from_time and upload_to_time are required")
        if payload.get("upload_from_time") >= payload.get("upload_to_time"):
            raise HTTPException(status_code=400, detail="upload_from_time must be less than upload_to_time")
        if payload.get("premium_study_material_discount") is not None and payload.get("premium_study_material_fee") is not None and payload.get("premium_study_material_discount") > payload.get("premium_study_material_fee"):
            raise HTTPException(status_code=400, detail="premium_study_material_discount cannot exceed premium_study_material_fee")

    maximum_students = payload.get("maximum_students")
    if maximum_students is not None and maximum_students <= 0:
        raise HTTPException(status_code=400, detail="maximum_students must be greater than 0")

    status_value = (payload.get("status") or TeachingSetupStatus.ACTIVE.value).upper()
    if status_value not in {TeachingSetupStatus.ACTIVE.value, TeachingSetupStatus.INACTIVE.value}:
        raise HTTPException(status_code=400, detail="status must be ACTIVE or INACTIVE")

    try:
        existing = (
            db.query(TuitionTeachingSetup)
            .filter(
                TuitionTeachingSetup.is_deleted.is_(False),
                TuitionTeachingSetup.lesson_plan_id == lesson_plan_id,
                TuitionTeachingSetup.status == TeachingSetupStatus.ACTIVE.value,
                TuitionTeachingSetup.teaching_mode == teaching_mode,
            )
        )
        if owner_user_id is not None:
            existing = existing.filter(TuitionTeachingSetup.created_by_user_id == owner_user_id)
        if owner_teacher_id:
            existing = existing.filter(TuitionTeachingSetup.created_by_teacher_id == owner_teacher_id)
        if owner_self_signed_teacher_id is not None:
            existing = existing.filter(TuitionTeachingSetup.created_by_self_signed_teacher_id == owner_self_signed_teacher_id)
        if payload.get("batch_id"):
            existing = existing.filter(TuitionTeachingSetup.batch_id == payload.get("batch_id"))
        if existing.first():
            raise HTTPException(status_code=400, detail="Duplicate active teaching setup for the same lesson plan and batch")
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Teaching setup database schema is not ready yet") from exc


def create_teaching_setup_service(
    db: Session,
    *,
    current_user,
    payload: TeachingSetupCreate,
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
):
    if getattr(current_user, "role", None) not in {UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN}:
        raise HTTPException(status_code=403, detail="Only teachers or admins can create teaching setup")

    try:
        payload_dict = payload.model_dump(exclude_unset=True)
        _validate_payload(
            db,
            payload_dict,
            owner_user_id=getattr(current_user, "id", None),
            owner_teacher_id=teacher_id or getattr(_safe_get_attribute(current_user, "teacher_profile"), "id", None),
            owner_self_signed_teacher_id=self_signed_teacher_id or getattr(_safe_get_attribute(current_user, "self_signed_teacher_profile"), "id", None),
        )

        owner_user_id = getattr(current_user, "id", None)
        owner_teacher_id = teacher_id or getattr(_safe_get_attribute(current_user, "teacher_profile"), "id", None)
        owner_self_signed_teacher_id = self_signed_teacher_id or getattr(_safe_get_attribute(current_user, "self_signed_teacher_profile"), "id", None)

        return crud_create_teaching_setup(
            db,
            payload=payload_dict,
            owner_user_id=owner_user_id,
            owner_teacher_id=owner_teacher_id,
            owner_self_signed_teacher_id=owner_self_signed_teacher_id,
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Teaching setup database schema is not ready yet") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create teaching setup") from exc


def update_teaching_setup_service(db: Session, *, teaching_setup: TuitionTeachingSetup, payload: TeachingSetupUpdate):
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")

    payload_dict = payload.model_dump(exclude_unset=True)
    merged_payload = {
        "lesson_plan_id": teaching_setup.lesson_plan_id,
        "teaching_mode": teaching_setup.teaching_mode,
        "batch_id": teaching_setup.batch_id,
        "batch_title": teaching_setup.batch_title,
        "batch_start_date": teaching_setup.batch_start_date,
        "batch_end_date": teaching_setup.batch_end_date,
        "tuition_from_time": teaching_setup.tuition_from_time,
        "tuition_to_time": teaching_setup.tuition_to_time,
        "tuition_days": teaching_setup.tuition_days,
        "languages": teaching_setup.languages,
        "subjects": teaching_setup.subjects,
        "material_update_days": teaching_setup.material_update_days,
        "upload_from_time": teaching_setup.upload_from_time,
        "upload_to_time": teaching_setup.upload_to_time,
        "monthly_tuition_fee": teaching_setup.monthly_tuition_fee,
        "monthly_tuition_discount": teaching_setup.monthly_tuition_discount,
        "premium_study_material_fee": teaching_setup.premium_study_material_fee,
        "premium_study_material_discount": teaching_setup.premium_study_material_discount,
        "maximum_students": teaching_setup.maximum_students,
        "meeting_provider": teaching_setup.meeting_provider,
        "meeting_link": teaching_setup.meeting_link,
        "online_teaching_ability": teaching_setup.online_teaching_ability,
        "stable_internet_connection": teaching_setup.stable_internet_connection,
        "camera_available": teaching_setup.camera_available,
        "silent_place_without_background_noise": teaching_setup.silent_place_without_background_noise,
        "laptop_desktop_pc": teaching_setup.laptop_desktop_pc,
        "headphone_whiteboard": teaching_setup.headphone_whiteboard,
        "status": teaching_setup.status,
    }
    merged_payload.update(payload_dict)

    _validate_payload(
        db,
        merged_payload,
        existing_setup_id=teaching_setup.id,
    )
    return crud_update_teaching_setup(db, teaching_setup, payload=payload_dict)


def get_tuition_setup_rating_summary(db: Session, teaching_setup_id: str) -> dict:
    row = (
        db.query(
            func.avg(TuitionTeachingSetupRating.rating).label("average_rating"),
            func.count(TuitionTeachingSetupRating.id).label("total_reviews"),
        )
        .filter(TuitionTeachingSetupRating.teaching_setup_id == teaching_setup_id)
        .one()
    )
    average_rating = round(float(row.average_rating or 0), 2) if row.average_rating is not None else 0.0
    total_reviews = int(row.total_reviews or 0)
    return {"average_rating": average_rating, "total_reviews": total_reviews}


def submit_teaching_setup_rating_service(
    db: Session,
    *,
    current_user,
    teaching_setup: TuitionTeachingSetup,
    payload: TeachingSetupRatingCreate,
):
    if not teaching_setup:
        raise HTTPException(status_code=404, detail="Teaching setup not found")

    if getattr(current_user, "role", None) == UserRole.STUDENT:
        student_user_id = getattr(current_user, "id", None)
        if student_user_id is None:
            raise HTTPException(status_code=400, detail="Student user id is missing")
        existing = (
            db.query(TuitionTeachingSetupRating)
            .filter(
                TuitionTeachingSetupRating.teaching_setup_id == teaching_setup.id,
                TuitionTeachingSetupRating.student_user_id == student_user_id,
            )
            .first()
        )
        if existing:
            existing.rating = payload.rating
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing

        rating = TuitionTeachingSetupRating(
            teaching_setup_id=teaching_setup.id,
            student_user_id=student_user_id,
            rating=payload.rating,
        )
        db.add(rating)
        db.commit()
        db.refresh(rating)
        return rating

    if getattr(current_user, "role", None) == UserRole.SELF_SIGNED_STUDENT:
        self_signed_student_profile = getattr(current_user, "self_signed_student_profile", None)
        self_signed_student_id = getattr(self_signed_student_profile, "id", None)
        if self_signed_student_id is None:
            raise HTTPException(status_code=400, detail="Self-signed student profile is missing")
        existing = (
            db.query(TuitionTeachingSetupRating)
            .filter(
                TuitionTeachingSetupRating.teaching_setup_id == teaching_setup.id,
                TuitionTeachingSetupRating.self_signed_student_id == self_signed_student_id,
            )
            .first()
        )
        if existing:
            existing.rating = payload.rating
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing

        rating = TuitionTeachingSetupRating(
            teaching_setup_id=teaching_setup.id,
            self_signed_student_id=self_signed_student_id,
            rating=payload.rating,
        )
        db.add(rating)
        db.commit()
        db.refresh(rating)
        return rating

    raise HTTPException(status_code=403, detail="Only students and self-signed students can rate a teaching setup")


def ensure_teacher_scope(current_user, *, teacher_id: Optional[str], self_signed_teacher_id: Optional[int]):
    if getattr(current_user, "role", None) in {UserRole.ADMIN, UserRole.SUPERADMIN}:
        return True

    current_teacher_id = getattr(getattr(current_user, "teacher_profile", None), "id", None)
    current_self_signed_teacher_id = getattr(getattr(current_user, "self_signed_teacher_profile", None), "id", None)

    if teacher_id is None and self_signed_teacher_id is None:
        if getattr(current_user, "role", None) == UserRole.TEACHER:
            return current_teacher_id is not None
        if getattr(current_user, "role", None) == UserRole.SELF_SIGNED_TEACHER:
            return current_self_signed_teacher_id is not None
        return False

    if teacher_id and current_teacher_id == teacher_id:
        return True
    if self_signed_teacher_id is not None and current_self_signed_teacher_id == self_signed_teacher_id:
        return True
    return False
