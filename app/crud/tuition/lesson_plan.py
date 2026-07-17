from typing import Optional
from sqlalchemy import func, update, case
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from app.models.tuition import (
    TuitionLessonPlan,
    TuitionLesson,
    TuitionLessonTopic,
    TuitionTopicFile,
    TuitionLessonPlanBatch,
    TuitionBatch,
    TuitionLessonAssignmentMapping,
)


def get_lesson_plan(db: Session, lesson_plan_id: str):
    return db.query(TuitionLessonPlan).filter(
        TuitionLessonPlan.id == lesson_plan_id,
        TuitionLessonPlan.is_deleted.is_(False),
    ).first()


def create_lesson_plan(db: Session, *, owner_user_id: Optional[int], owner_teacher_id: Optional[str], owner_self_signed_teacher_id: Optional[int], board_id: str, class_id: int, subject_id: int, title: Optional[str], batch_ids: list[str], merge_existing: bool = False, existing_lesson_plan: Optional[TuitionLessonPlan] = None):
    batch_ids = [batch_id for batch_id in batch_ids if batch_id]
    primary_batch_id = batch_ids[0] if batch_ids else None
    if not primary_batch_id:
        raise ValueError("At least one batch is required to create a lesson plan")

    if merge_existing and existing_lesson_plan is not None:
        existing_lesson_plan.lesson_title = title or existing_lesson_plan.lesson_title or "Untitled Lesson Plan"
        existing_lesson_plan.chapter = title or existing_lesson_plan.chapter
        existing_lesson_plan.batch_id = existing_lesson_plan.batch_id or primary_batch_id
        existing_lesson_plan.status = "active"

        existing_batch_ids = {mapping.batch_id for mapping in getattr(existing_lesson_plan, "batch_mappings", []) if getattr(mapping, "batch_id", None)}
        for batch_id in batch_ids:
            if batch_id not in existing_batch_ids:
                mapping = TuitionLessonPlanBatch(lesson_plan_id=existing_lesson_plan.id, batch_id=batch_id)
                db.add(mapping)
                existing_batch_ids.add(batch_id)

        db.commit()
        db.refresh(existing_lesson_plan)
        return existing_lesson_plan

    lesson_plan = TuitionLessonPlan(
        batch_id=primary_batch_id,
        chapter=title,
        lesson_title=title or "Untitled Lesson Plan",
        objective=None,
        status="active",
    )
    db.add(lesson_plan)
    db.flush()

    for batch_id in batch_ids:
        mapping = TuitionLessonPlanBatch(
            lesson_plan_id=lesson_plan.id,
            batch_id=batch_id,
        )
        db.add(mapping)

    db.commit()
    db.refresh(lesson_plan)
    return lesson_plan


def update_lesson_plan(db: Session, lesson_plan: TuitionLessonPlan, **kwargs):
    batch_ids = kwargs.pop("batch_ids", None)
    if batch_ids is not None:
        existing_batch_ids = {mapping.batch_id for mapping in lesson_plan.batch_mappings if getattr(mapping, 'batch_id', None)}
        for batch_id in [batch_id for batch_id in batch_ids if batch_id]:
            if batch_id not in existing_batch_ids:
                lesson_plan.batch_mappings.append(
                    TuitionLessonPlanBatch(lesson_plan_id=lesson_plan.id, batch_id=batch_id)
                )
                existing_batch_ids.add(batch_id)
        if not lesson_plan.batch_id and lesson_plan.batch_mappings:
            lesson_plan.batch_id = lesson_plan.batch_mappings[0].batch_id

    for key, value in kwargs.items():
        if value is None:
            continue
        attr = getattr(type(lesson_plan), key, None)
        if isinstance(attr, property) and attr.fset is None:
            continue
        if not hasattr(lesson_plan, key):
            continue
        try:
            setattr(lesson_plan, key, value)
        except AttributeError:
            continue

    db.add(lesson_plan)
    db.commit()
    db.refresh(lesson_plan)
    return lesson_plan


def delete_lesson_plan(db: Session, lesson_plan: TuitionLessonPlan):
    lesson_plan.is_deleted = True
    lesson_plan.deleted_at = lesson_plan.updated_at
    db.commit()
    return lesson_plan


def create_lesson(db: Session, *, lesson_plan_id: str, lesson_title: str, lesson_objective: Optional[str], display_order: Optional[int] = None):
    if display_order is None:
        max_order = db.query(func.max(TuitionLesson.display_order)).filter(
            TuitionLesson.lesson_plan_id == lesson_plan_id,
            TuitionLesson.is_deleted.is_(False),
        ).scalar()
        display_order = (max_order or 0) + 1

    lesson = TuitionLesson(
        lesson_plan_id=lesson_plan_id,
        lesson_title=lesson_title,
        lesson_objective=lesson_objective,
        display_order=display_order,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def get_lesson(db: Session, lesson_id: str):
    return (
        db.query(TuitionLesson)
        .options(selectinload(TuitionLesson.topics))
        .filter(TuitionLesson.id == lesson_id, TuitionLesson.is_deleted.is_(False))
        .first()
    )


def delete_lesson(db: Session, lesson: TuitionLesson):
    lesson.is_deleted = True
    lesson.deleted_at = lesson.updated_at
    db.commit()
    return lesson


def create_topic(db: Session, *, lesson_id: str, topic_title: str, topic_content: Optional[str], reference_video_link: Optional[str], display_order: Optional[int] = None):
    if display_order is None:
        # include soft-deleted topics when calculating next display_order
        max_order = db.query(func.max(TuitionLessonTopic.display_order)).filter(
            TuitionLessonTopic.lesson_id == lesson_id,
        ).scalar()
        display_order = (max_order or 0) + 1

    # Attempt to insert, retrying if a unique constraint on (lesson_id, display_order) is hit.
    attempts = 5
    for attempt in range(attempts):
        topic = TuitionLessonTopic(
            lesson_id=lesson_id,
            topic_title=topic_title,
            topic_content=topic_content,
            reference_video_link=reference_video_link,
            display_order=display_order,
        )
        db.add(topic)
        try:
            db.commit()
            db.refresh(topic)
            return topic
        except IntegrityError:
            # likely a duplicate display_order (race). roll back and recompute next order, then retry.
            db.rollback()
            # recompute considering soft-deleted rows so we don't reuse an occupied display_order
            max_order = db.query(func.max(TuitionLessonTopic.display_order)).filter(
                TuitionLessonTopic.lesson_id == lesson_id,
            ).scalar()
            display_order = (max_order or 0) + 1
            # try again
            continue
    # If we reach here, fail with a clear runtime error so the caller can handle it.
    raise RuntimeError("Could not allocate unique display_order for topic after retries")


def get_topic(db: Session, topic_id: str):
    return db.query(TuitionLessonTopic).filter(TuitionLessonTopic.id == topic_id, TuitionLessonTopic.is_deleted.is_(False)).first()


def delete_topic(db: Session, topic: TuitionLessonTopic):
    # soft-delete the topic
    topic.is_deleted = True
    topic.deleted_at = topic.updated_at
    db.commit()

    # compact/renumber remaining topics' display_order for this lesson
    remaining = (
        db.query(TuitionLessonTopic)
        .filter(TuitionLessonTopic.lesson_id == topic.lesson_id, TuitionLessonTopic.is_deleted.is_(False))
        .order_by(TuitionLessonTopic.display_order)
        .all()
    )
    for idx, t in enumerate(remaining, start=1):
        if t.display_order != idx:
            t.display_order = idx
    db.commit()
    return topic


def reorder_topics(db: Session, lesson_id: str, topic_updates: list[dict]):
    # Load current non-deleted topics in order
    current = (
        db.query(TuitionLessonTopic)
        .filter(TuitionLessonTopic.lesson_id == lesson_id, TuitionLessonTopic.is_deleted.is_(False))
        .order_by(TuitionLessonTopic.display_order)
        .all()
    )
    if not current:
        return True

    # Build an ordered list of ids
    ordered_ids = [t.id for t in current]

    # Apply updates by removing moved ids and inserting them at requested positions
    for item in topic_updates:
        tid = item.get('topic_id')
        pos = max(1, int(item.get('display_order', 1)))
        # remove if exists
        if tid in ordered_ids:
            ordered_ids.remove(tid)
        # insert at position (1-based -> 0-based index)
        insert_idx = min(len(ordered_ids), max(0, pos - 1))
        ordered_ids.insert(insert_idx, tid)

    # Now compute final contiguous display orders
    final_mapping = {tid: idx + 1 for idx, tid in enumerate(ordered_ids)}

    # To avoid unique-constraint conflicts when swapping values, perform a two-step update:
    # 1) add a large offset to all current display_order values for this lesson
    # 2) set the final display_order values using a CASE expression
    max_order = db.query(func.max(TuitionLessonTopic.display_order)).filter(TuitionLessonTopic.lesson_id == lesson_id).scalar()
    offset = (max_order or 0) + len(final_mapping) + 5

    # Step 1: add offset to all topics in this lesson
    stmt_offset = (
        update(TuitionLessonTopic)
        .where(TuitionLessonTopic.lesson_id == lesson_id)
        .values(display_order=TuitionLessonTopic.display_order + offset)
    )
    db.execute(stmt_offset)

    # Step 2: set final values (small numbers) for all affected topics
    stmt = (
        update(TuitionLessonTopic)
        .where(TuitionLessonTopic.lesson_id == lesson_id, TuitionLessonTopic.id.in_(list(final_mapping.keys())))
        .values(
            display_order=case(final_mapping, value=TuitionLessonTopic.id),
            updated_at=datetime.utcnow(),
        )
    )
    db.execute(stmt)
    db.commit()
    return True


def create_topic_file(db: Session, *, topic_id: str, file_name: str, file_url: str, file_type: Optional[str], uploader: dict):
    file_record = TuitionTopicFile(
        topic_id=topic_id,
        file_name=file_name,
        file_url=file_url,
        file_type=file_type,
        uploaded_by_user_id=uploader.get('user_id'),
        uploaded_by_teacher_id=uploader.get('teacher_id'),
        uploaded_by_self_signed_teacher_id=uploader.get('self_signed_teacher_id'),
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record


def delete_topic_file(db: Session, file_record: TuitionTopicFile):
    file_record.is_deleted = True
    file_record.deleted_at = file_record.created_at
    db.commit()
    return file_record


def get_topic_files(db: Session, topic_id: str):
    return db.query(TuitionTopicFile).filter(TuitionTopicFile.topic_id == topic_id, TuitionTopicFile.is_deleted.is_(False)).all()


def list_lesson_plans_for_user(db: Session, *, created_by_user_id: Optional[int], created_by_teacher_id: Optional[str], created_by_self_signed_teacher_id: Optional[int], status: Optional[str] = None, board_id: Optional[str] = None, class_id: Optional[int] = None, subject_id: Optional[int] = None, search: Optional[str] = None):
    # Join through the lesson-plan-to-batch mapping table so each plan can belong to multiple batches.
    query = (
        db.query(TuitionLessonPlan.id)
        .join(TuitionLessonPlanBatch, TuitionLessonPlan.id == TuitionLessonPlanBatch.lesson_plan_id)
        .join(TuitionBatch, TuitionLessonPlanBatch.batch_id == TuitionBatch.id)
        .filter(TuitionLessonPlan.is_deleted.is_(False))
    )
    if created_by_teacher_id is not None:
        query = query.filter(TuitionBatch.teacher_id == created_by_teacher_id)
    elif created_by_self_signed_teacher_id is not None:
        query = query.filter(TuitionBatch.self_signed_teacher_id == created_by_self_signed_teacher_id)
    elif created_by_user_id is not None:
        query = query.filter(TuitionBatch.created_by_user_id == created_by_user_id)
    if status:
        query = query.filter(TuitionLessonPlan.status == status)
    if board_id:
        query = query.filter(TuitionBatch.board_id == board_id)
    if class_id:
        query = query.filter(TuitionBatch.class_id == class_id)
    if subject_id:
        query = query.filter(TuitionBatch.subject_id == subject_id)
    if search:
        search_text = f"%{search}%"
        query = query.filter(
            TuitionLessonPlan.lesson_title.ilike(search_text) |
            TuitionLessonPlan.chapter.ilike(search_text)
        )

    lesson_plan_ids = [row[0] for row in query.distinct(TuitionLessonPlan.id).all()]
    if not lesson_plan_ids:
        return []

    return (
        db.query(TuitionLessonPlan)
        .options(selectinload(TuitionLessonPlan.lessons))
        .filter(TuitionLessonPlan.id.in_(lesson_plan_ids))
        .order_by(TuitionLessonPlan.created_at.desc())
        .all()
    )
