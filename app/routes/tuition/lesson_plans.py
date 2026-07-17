from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.tuition import TuitionLessonPlan, TuitionLesson, TuitionLessonTopic, TuitionTopicFile
from app.models.teachers import SelfSignedTeacherTeachingConfiguration, TeacherClassSectionSubject
from app.models.school import Class, Subject
from app.models.admin import SchoolClassSubject
from app.schemas.tuition.lesson_plan import (
    LessonPlanCreate,
    LessonPlanCreateResponse,
    LessonPlanResponse,
    LessonCreate,
    LessonUpdate,
    TopicCreate,
    TopicUpdate,
    TopicReorderRequest,
    TopicFileResponse,
    LessonResponse,
    LessonSummaryResponse,
    TopicResponse,
    LessonPlanUpdate,
)
from app.schemas.users import UserRole
from app.utils.permission import require_roles
from app.crud.tuition.lesson_plan import (
    create_lesson_plan,
    get_lesson_plan,
    delete_lesson_plan,
    create_lesson,
    get_lesson,
    delete_lesson,
    create_topic,
    get_topic,
    delete_topic,
    reorder_topics,
    create_topic_file,
    delete_topic_file,
    get_topic_files,
    list_lesson_plans_for_user,
)
from app.services.tuition.lesson_plan import (
    can_edit_lesson_plan,
    can_delete_lesson_plan,
    create_lesson_plan_service,
    update_lesson_plan_service,
)
from app.utils.s3 import upload_multipart_file_to_s3

router = APIRouter(prefix="/tuition", tags=["Tuition"])


def _get_lesson_plan_or_404(db: Session, lesson_plan_id: str):
    lesson_plan = get_lesson_plan(db, lesson_plan_id)
    if not lesson_plan:
        raise HTTPException(status_code=404, detail="Lesson plan not found")
    return lesson_plan


def _choose_self_signed_teacher_class_subject(db: Session, current_user: object, lesson_plan: TuitionLessonPlan):
    teacher = getattr(current_user, 'self_signed_teacher_profile', None)
    if not teacher:
        return lesson_plan.class_name, lesson_plan.subject_name

    configs = (
        db.query(SelfSignedTeacherTeachingConfiguration)
        .filter(
            SelfSignedTeacherTeachingConfiguration.self_signed_teacher_id == teacher.id,
            SelfSignedTeacherTeachingConfiguration.is_active.is_(True),
        )
        .all()
    )
    if not configs:
        return lesson_plan.class_name, lesson_plan.subject_name

    preferred = None
    if len(configs) == 1:
        preferred = configs[0]
    else:
        board_value = lesson_plan.board
        for cfg in configs:
            if cfg.board_id and board_value and str(cfg.board_id).lower() == str(board_value).lower():
                preferred = cfg
                break
        preferred = preferred or configs[0]

    class_group = db.query(SchoolClassSubject).filter(SchoolClassSubject.id == preferred.class_id).first()
    subject_name = None
    if preferred.subject_ids:
        subject_row = (
            db.query(SchoolClassSubject)
            .filter(SchoolClassSubject.id == preferred.subject_ids[0])
            .first()
        )
        subject_name = subject_row.subject if subject_row else None

    return class_group.class_name if class_group else lesson_plan.class_name, subject_name or lesson_plan.subject_name


def _choose_school_teacher_class_subject(db: Session, current_user: object, lesson_plan: TuitionLessonPlan):
    teacher = getattr(current_user, 'teacher_profile', None)
    if not teacher:
        return lesson_plan.class_name, lesson_plan.subject_name

    school = getattr(teacher, 'school', None)
    board_value = None
    if school and getattr(school, 'school_board', None):
        board_value = str(school.school_board.value if hasattr(school.school_board, 'value') else school.school_board)

    mapping = (
        db.query(TeacherClassSectionSubject)
        .join(Class, TeacherClassSectionSubject.class_id == Class.id)
        .join(Subject, TeacherClassSectionSubject.subject_id == Subject.id)
        .filter(TeacherClassSectionSubject.teacher_id == teacher.id)
        .first()
    )
    if not mapping:
        return lesson_plan.class_name, lesson_plan.subject_name

    cls_name = mapping.class_.name if mapping.class_ else None
    subj_name = mapping.subject.name if mapping.subject else None
    return cls_name or lesson_plan.class_name, subj_name or lesson_plan.subject_name


def _map_lesson_plan_response(db: Session, lesson_plan: TuitionLessonPlan, current_user: object):
    class_name, subject_name = lesson_plan.class_name, lesson_plan.subject_name
    if getattr(current_user, 'role', None) == UserRole.SELF_SIGNED_TEACHER:
        class_name, subject_name = _choose_self_signed_teacher_class_subject(db, current_user, lesson_plan)
    elif getattr(current_user, 'role', None) == UserRole.TEACHER:
        class_name, subject_name = _choose_school_teacher_class_subject(db, current_user, lesson_plan)

    lesson_items = [
        LessonSummaryResponse(
            id=lesson.id,
            lesson_title=lesson.lesson_title,
            lesson_objective=lesson.lesson_objective,
            display_order=lesson.display_order,
            created_at=lesson.created_at,
            updated_at=lesson.updated_at,
        )
        for lesson in sorted(lesson_plan.lessons, key=lambda lesson: lesson.display_order)
    ]

    return {
        'id': lesson_plan.id,
        'title': lesson_plan.title,
        'board': lesson_plan.board,
        'class_id': lesson_plan.class_id,
        'class_name': class_name,
        'subject_id': lesson_plan.subject_id,
        'subject_name': subject_name,
        'batch_ids': lesson_plan.batch_ids,
        'batches': [
            {'id': batch.id, 'batch_name': batch.batch_name}
            for batch in lesson_plan.batches
        ],
        'lessons': lesson_items,
        'status': lesson_plan.status,
        'remarks': lesson_plan.remarks,
        'created_at': lesson_plan.created_at,
        'updated_at': lesson_plan.updated_at,
    }


def _get_lesson_or_404(db: Session, lesson_id: str):
    lesson = get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def _get_topic_or_404(db: Session, topic_id: str):
    topic = get_topic(db, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/lesson-plans", response_model=LessonPlanCreateResponse)
def create_lesson_plan_endpoint(
    payload: LessonPlanCreate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    lesson_plan = create_lesson_plan_service(db, current_user=current_user, payload=payload)
    return LessonPlanCreateResponse(message="Lesson plan created successfully.", lesson_plan_id=lesson_plan.id, status=str(lesson_plan.status))


@router.put("/lesson-plans/{lesson_plan_id}", response_model=LessonPlanResponse)
def update_lesson_plan_endpoint(
    lesson_plan_id: str,
    payload: LessonPlanUpdate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    lesson_plan = _get_lesson_plan_or_404(db, lesson_plan_id)
    if not can_edit_lesson_plan(lesson_plan):
        raise HTTPException(status_code=403, detail="Only active lesson plans can be updated")
    updated = update_lesson_plan_service(db, lesson_plan, current_user=current_user, payload=payload)
    return updated


@router.get("/lesson-plans/my", response_model=list[LessonPlanResponse])
def my_lesson_plans(
    teacher_id: Optional[str] = None,
    self_signed_teacher_id: Optional[int] = None,
    status: Optional[str] = None,
    board: Optional[str] = None,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    if getattr(current_user, 'role', None) in {UserRole.ADMIN, UserRole.SUPERADMIN} and (teacher_id or self_signed_teacher_id):
        owner_user_id = None
        owner_teacher_id = teacher_id
        owner_self_signed_teacher_id = self_signed_teacher_id
    else:
        owner_user_id = current_user.id
        owner_teacher_id = getattr(current_user.teacher_profile, 'id', None) if getattr(current_user, 'teacher_profile', None) else None
        owner_self_signed_teacher_id = getattr(current_user.self_signed_teacher_profile, 'id', None) if getattr(current_user, 'self_signed_teacher_profile', None) else None
    items = list_lesson_plans_for_user(
        db,
        created_by_user_id=owner_user_id,
        created_by_teacher_id=owner_teacher_id,
        created_by_self_signed_teacher_id=owner_self_signed_teacher_id,
        status=status,
        board_id=board,
        class_id=class_id,
        subject_id=subject_id,
        search=search,
    )
    return [_map_lesson_plan_response(db, item, current_user) for item in items]


@router.get("/lesson-plans/{lesson_plan_id}", response_model=LessonPlanResponse)
def lesson_plan_detail(lesson_plan_id: str, db: Session = Depends(get_db)):
    lesson_plan = _get_lesson_plan_or_404(db, lesson_plan_id)
    return lesson_plan


@router.delete("/lesson-plans/{lesson_plan_id}", status_code=status.HTTP_200_OK)
def delete_lesson_plan_endpoint(lesson_plan_id: str, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    lesson_plan = _get_lesson_plan_or_404(db, lesson_plan_id)
    if not can_delete_lesson_plan(lesson_plan):
        raise HTTPException(status_code=403, detail="Only active lesson plans can be deleted")
    delete_lesson_plan(db, lesson_plan)
    return {"message": "Lesson plan deleted successfully."}


@router.post("/lesson-plans/{lesson_plan_id}/lessons", response_model=LessonResponse)
def create_lesson_endpoint(
    lesson_plan_id: str,
    payload: LessonCreate,
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    lesson_plan = _get_lesson_plan_or_404(db, lesson_plan_id)
    if not can_edit_lesson_plan(lesson_plan):
        raise HTTPException(status_code=403, detail="Lessons can only be changed for active lesson plans")
    lesson = create_lesson(db, lesson_plan_id=lesson_plan_id, lesson_title=payload.lesson_title, lesson_objective=payload.lesson_objective)
    return lesson


@router.put("/lesson-plans/lessons/{lesson_id}", response_model=LessonResponse)
def update_lesson_endpoint(lesson_id: str, payload: LessonUpdate, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    lesson = _get_lesson_or_404(db, lesson_id)
    if not can_edit_lesson_plan(lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Lessons can only be changed for active lesson plans")
    if payload.lesson_title is not None:
        lesson.lesson_title = payload.lesson_title
    if payload.lesson_objective is not None:
        lesson.lesson_objective = payload.lesson_objective
    db.commit()
    db.refresh(lesson)
    return lesson


@router.delete("/lesson-plans/lessons/{lesson_id}", status_code=status.HTTP_200_OK)
def delete_lesson_endpoint(lesson_id: str, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    lesson = _get_lesson_or_404(db, lesson_id)
    if not can_edit_lesson_plan(lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Lessons can only be deleted for active lesson plans")
    delete_lesson(db, lesson)
    return {"message": "Lesson deleted successfully."}


@router.get("/lesson-plans/lessons/{lesson_id}", response_model=LessonResponse)
def lesson_detail(lesson_id: str, db: Session = Depends(get_db)):
    lesson = _get_lesson_or_404(db, lesson_id)
    topics = [
        TopicResponse(
            id=topic.id,
            lesson_id=topic.lesson_id,
            topic_title=topic.topic_title,
            topic_content=topic.topic_content,
            display_order=topic.display_order,
            reference_video_link=topic.reference_video_link,
            created_at=topic.created_at,
            updated_at=topic.updated_at,
        )
        for topic in sorted(lesson.topics, key=lambda topic: topic.display_order)
        if not getattr(topic, "is_deleted", False)
    ]
    return LessonResponse(
        id=lesson.id,
        lesson_plan_id=lesson.lesson_plan_id,
        lesson_title=lesson.lesson_title,
        lesson_objective=lesson.lesson_objective,
        display_order=lesson.display_order,
        topics=topics,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
    )


@router.post("/lesson-plans/lessons/{lesson_id}/topics", response_model=TopicResponse)
def create_topic_endpoint(lesson_id: str, payload: TopicCreate, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    lesson = _get_lesson_or_404(db, lesson_id)
    if not can_edit_lesson_plan(lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topics can only be changed for active lesson plans")
    topic = create_topic(db, lesson_id=lesson_id, topic_title=payload.topic_title, topic_content=payload.topic_content, reference_video_link=payload.reference_video_link)
    return topic


@router.put("/lesson-plans/topics/{topic_id}", response_model=TopicResponse)
def update_topic_endpoint(topic_id: str, payload: TopicUpdate, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    topic = _get_topic_or_404(db, topic_id)
    if not can_edit_lesson_plan(topic.lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topics can only be changed for active lesson plans")
    if payload.topic_title is not None:
        topic.topic_title = payload.topic_title
    if payload.topic_content is not None:
        topic.topic_content = payload.topic_content
    if payload.reference_video_link is not None:
        topic.reference_video_link = payload.reference_video_link
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/lesson-plans/topics/{topic_id}", status_code=status.HTTP_200_OK)
def delete_topic_endpoint(topic_id: str, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    topic = _get_topic_or_404(db, topic_id)
    if not can_edit_lesson_plan(topic.lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topics can only be deleted for active lesson plans")
    delete_topic(db, topic)
    return {"message": "Topic deleted successfully."}


@router.patch("/lesson-plans/lessons/{lesson_id}/topics/reorder")
def reorder_topic_endpoint(lesson_id: str, payload: TopicReorderRequest, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    lesson = _get_lesson_or_404(db, lesson_id)
    if not can_edit_lesson_plan(lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topics can only be reordered for active lesson plans")
    reorder_topics(db, lesson_id, [item.model_dump() for item in payload.topics])
    return {"message": "Topics reordered successfully."}


@router.get("/lesson-plans/topics/{topic_id}", response_model=TopicResponse)
def topic_detail(topic_id: str, db: Session = Depends(get_db)):
    return _get_topic_or_404(db, topic_id)


@router.post("/lesson-plans/topics/{topic_id}/files", response_model=TopicFileResponse)
def upload_topic_file_endpoint(
    topic_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN)),
):
    topic = _get_topic_or_404(db, topic_id)
    if not can_edit_lesson_plan(topic.lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topic files can only be uploaded for active lesson plans")
    url = upload_multipart_file_to_s3(file, f"tuition/topic/{topic_id}")
    file_record = create_topic_file(db, topic_id=topic_id, file_name=file.filename or "file", file_url=url, file_type=file.content_type, uploader={
        'user_id': getattr(current_user, 'id', None),
        'teacher_id': getattr(getattr(current_user, 'teacher_profile', None), 'id', None),
        'self_signed_teacher_id': getattr(getattr(current_user, 'self_signed_teacher_profile', None), 'id', None),
    })
    return file_record


@router.delete("/lesson-plans/topics/files/{file_id}", status_code=status.HTTP_200_OK)
def delete_topic_file_endpoint(file_id: str, db: Session = Depends(get_db), current_user: object = Depends(require_roles(UserRole.TEACHER, UserRole.SELF_SIGNED_TEACHER, UserRole.ADMIN, UserRole.SUPERADMIN))):
    file_record = db.query(TuitionTopicFile).filter(TuitionTopicFile.id == file_id, TuitionTopicFile.is_deleted.is_(False)).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Topic file not found")
    if not can_edit_lesson_plan(file_record.topic.lesson.lesson_plan):
        raise HTTPException(status_code=403, detail="Topic files can only be deleted for active lesson plans")
    delete_topic_file(db, file_record)
    return {"message": "Topic file deleted successfully."}


@router.get("/lesson-plans/topics/{topic_id}/files", response_model=list[TopicFileResponse])
def topic_files_list(topic_id: str, db: Session = Depends(get_db)):
    return get_topic_files(db, topic_id)


