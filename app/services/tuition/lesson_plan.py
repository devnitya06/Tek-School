from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.crud.tuition.lesson_plan import (
    create_lesson_plan as crud_create_lesson_plan,
    update_lesson_plan as crud_update_lesson_plan,
)
from app.models.tuition import TuitionLessonPlan, LessonPlanStatus, TuitionBatch, TuitionLessonPlanBatch
from app.schemas.tuition.lesson_plan import LessonPlanCreate, LessonPlanUpdate


def merge_lesson_plan_batches(lesson_plan: TuitionLessonPlan, batch_ids: list[str]) -> TuitionLessonPlan:
    existing_batch_ids = {mapping.batch_id for mapping in getattr(lesson_plan, "batch_mappings", []) if getattr(mapping, "batch_id", None)}
    for batch_id in batch_ids:
        if batch_id not in existing_batch_ids:
            lesson_plan.batch_mappings.append(TuitionLessonPlanBatch(lesson_plan_id=lesson_plan.id, batch_id=batch_id))
            existing_batch_ids.add(batch_id)
    if lesson_plan.batch_mappings:
        lesson_plan.batch_id = lesson_plan.batch_mappings[0].batch_id
    return lesson_plan


def can_edit_lesson_plan(lesson_plan: TuitionLessonPlan) -> bool:
    if lesson_plan is None:
        return False
    return str(lesson_plan.status) in {LessonPlanStatus.DRAFT.value, LessonPlanStatus.REJECTED.value}


def can_delete_lesson_plan(lesson_plan: TuitionLessonPlan) -> bool:
    if lesson_plan is None:
        return False
    return str(lesson_plan.status) in {LessonPlanStatus.DRAFT.value, LessonPlanStatus.REJECTED.value}


def _resolve_lesson_plan_batch_ids(
    db: Session,
    batch_inputs: list[str],
    board: str,
    class_id: int,
    subject_id: int,
    owner_teacher_id: Optional[str],
    owner_self_signed_teacher_id: Optional[int],
) -> list[str]:
    resolved_batch_ids: list[str] = []
    for ident in batch_inputs:
        batch = db.query(TuitionBatch).filter(TuitionBatch.id == ident, TuitionBatch.is_deleted.is_(False)).first()
        if batch:
            resolved_batch_ids.append(batch.id)
            continue

        if not board or not class_id or not subject_id:
            raise HTTPException(
                status_code=400,
                detail="batch_ids that are not existing IDs require board, class_id and subject_id to resolve names",
            )

        batch_query = db.query(TuitionBatch).filter(
            TuitionBatch.board_id == board,
            TuitionBatch.class_id == class_id,
            TuitionBatch.subject_id == subject_id,
            TuitionBatch.is_deleted.is_(False),
        )
        if owner_teacher_id:
            batch_query = batch_query.filter(TuitionBatch.teacher_id == owner_teacher_id)
        elif owner_self_signed_teacher_id:
            batch_query = batch_query.filter(TuitionBatch.self_signed_teacher_id == owner_self_signed_teacher_id)

        existing_count = batch_query.count()
        if existing_count >= 3:
            raise HTTPException(
                status_code=400,
                detail="Maximum 3 batches allowed for this board/class/subject for this teacher",
            )

        batch_by_name = batch_query.filter(TuitionBatch.batch_name == ident).first()
        if batch_by_name:
            resolved_batch_ids.append(batch_by_name.id)
            continue

        new_batch = TuitionBatch(
            batch_name=ident,
            board_id=board,
            class_id=class_id,
            subject_id=subject_id,
            teacher_id=owner_teacher_id if owner_teacher_id else None,
            self_signed_teacher_id=owner_self_signed_teacher_id if owner_self_signed_teacher_id else None,
            created_by_user_id=owner_teacher_id if owner_teacher_id else None,
        )
        db.add(new_batch)
        db.flush()
        resolved_batch_ids.append(new_batch.id)

    return resolved_batch_ids


def create_lesson_plan_service(db: Session, *, current_user, payload: LessonPlanCreate):
    owner_user_id = current_user.id if current_user else None
    owner_teacher_id = getattr(current_user.teacher_profile, 'id', None) if getattr(current_user, 'teacher_profile', None) else None
    owner_self_signed_teacher_id = getattr(current_user.self_signed_teacher_profile, 'id', None) if getattr(current_user, 'self_signed_teacher_profile', None) else None
    resolved_batch_ids = _resolve_lesson_plan_batch_ids(
        db,
        payload.batch_ids or [],
        payload.board,
        payload.class_id,
        payload.subject_id,
        owner_teacher_id,
        owner_self_signed_teacher_id,
    )

    existing_plan = (
        db.query(TuitionLessonPlan)
        .join(TuitionLessonPlanBatch, TuitionLessonPlan.id == TuitionLessonPlanBatch.lesson_plan_id)
        .join(TuitionBatch, TuitionLessonPlanBatch.batch_id == TuitionBatch.id)
        .filter(
            TuitionLessonPlan.is_deleted.is_(False),
            TuitionLessonPlan.status == LessonPlanStatus.DRAFT.value,
            TuitionLessonPlan.lesson_title == (payload.title or "Untitled Lesson Plan"),
            TuitionBatch.board_id == payload.board,
            TuitionBatch.class_id == payload.class_id,
            TuitionBatch.subject_id == payload.subject_id,
        )
    )
    if owner_teacher_id:
        existing_plan = existing_plan.filter(TuitionBatch.teacher_id == owner_teacher_id)
    elif owner_self_signed_teacher_id:
        existing_plan = existing_plan.filter(TuitionBatch.self_signed_teacher_id == owner_self_signed_teacher_id)
    existing_plan = existing_plan.first()

    if existing_plan is not None:
        return crud_create_lesson_plan(
            db,
            owner_user_id=owner_user_id,
            owner_teacher_id=owner_teacher_id,
            owner_self_signed_teacher_id=owner_self_signed_teacher_id,
            board_id=payload.board,
            class_id=payload.class_id,
            subject_id=payload.subject_id,
            title=payload.title,
            batch_ids=resolved_batch_ids,
            merge_existing=True,
            existing_lesson_plan=existing_plan,
        )

    return crud_create_lesson_plan(
        db,
        owner_user_id=owner_user_id,
        owner_teacher_id=owner_teacher_id,
        owner_self_signed_teacher_id=owner_self_signed_teacher_id,
        board_id=payload.board,
        class_id=payload.class_id,
        subject_id=payload.subject_id,
        title=payload.title,
        batch_ids=resolved_batch_ids,
    )


def update_lesson_plan_service(db: Session, lesson_plan: TuitionLessonPlan, *, current_user, payload: 'LessonPlanUpdate'):
    owner_user_id = current_user.id if current_user else None
    owner_teacher_id = getattr(current_user.teacher_profile, 'id', None) if getattr(current_user, 'teacher_profile', None) else None
    owner_self_signed_teacher_id = getattr(current_user.self_signed_teacher_profile, 'id', None) if getattr(current_user, 'self_signed_teacher_profile', None) else None

    kwargs = payload.model_dump(exclude_unset=True)
    board = kwargs.pop('board', None)
    class_id = kwargs.pop('class_id', None)
    subject_id = kwargs.pop('subject_id', None)

    if payload.batch_ids is not None:
        if board is None or class_id is None or subject_id is None:
            first_batch = lesson_plan.batches[0] if lesson_plan.batches else None
            if first_batch is not None:
                board = board or first_batch.board_id
                class_id = class_id or first_batch.class_id
                subject_id = subject_id or first_batch.subject_id

        kwargs['batch_ids'] = _resolve_lesson_plan_batch_ids(
            db,
            payload.batch_ids,
            board,
            class_id,
            subject_id,
            owner_teacher_id,
            owner_self_signed_teacher_id,
        )

    return crud_update_lesson_plan(db, lesson_plan, **kwargs)


def submit_lesson_plan_service(lesson_plan: TuitionLessonPlan):
    lesson_plan.status = LessonPlanStatus.SUBMITTED.value
    return lesson_plan


def withdraw_lesson_plan_service(lesson_plan: TuitionLessonPlan):
    lesson_plan.status = LessonPlanStatus.DRAFT.value
    return lesson_plan


def approve_lesson_plan_service(lesson_plan: TuitionLessonPlan):
    lesson_plan.status = LessonPlanStatus.APPROVED.value
    return lesson_plan


def reject_lesson_plan_service(lesson_plan: TuitionLessonPlan):
    lesson_plan.status = LessonPlanStatus.REJECTED.value
    return lesson_plan
