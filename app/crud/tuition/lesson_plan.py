from typing import Optional
from sqlalchemy.orm import Session
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
        existing_lesson_plan.status = "draft"

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
        status="draft",
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


def create_lesson(db: Session, *, lesson_plan_id: str, lesson_title: str, lesson_objective: Optional[str], display_order: int):
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
    return db.query(TuitionLesson).filter(TuitionLesson.id == lesson_id, TuitionLesson.is_deleted.is_(False)).first()


def delete_lesson(db: Session, lesson: TuitionLesson):
    lesson.is_deleted = True
    lesson.deleted_at = lesson.updated_at
    db.commit()
    return lesson


def create_topic(db: Session, *, lesson_id: str, topic_title: str, topic_content: Optional[str], reference_video_link: Optional[str], display_order: int):
    topic = TuitionLessonTopic(
        lesson_id=lesson_id,
        topic_title=topic_title,
        topic_content=topic_content,
        reference_video_link=reference_video_link,
        display_order=display_order,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def get_topic(db: Session, topic_id: str):
    return db.query(TuitionLessonTopic).filter(TuitionLessonTopic.id == topic_id, TuitionLessonTopic.is_deleted.is_(False)).first()


def delete_topic(db: Session, topic: TuitionLessonTopic):
    topic.is_deleted = True
    topic.deleted_at = topic.updated_at
    db.commit()
    return topic


def reorder_topics(db: Session, lesson_id: str, topic_updates: list[dict]):
    for item in topic_updates:
        topic = db.query(TuitionLessonTopic).filter(TuitionLessonTopic.id == item['topic_id'], TuitionLessonTopic.lesson_id == lesson_id).first()
        if topic:
            topic.display_order = item['display_order']
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
        .filter(TuitionLessonPlan.id.in_(lesson_plan_ids))
        .order_by(TuitionLessonPlan.created_at.desc())
        .all()
    )
