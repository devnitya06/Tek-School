"""Student Tuition Routes - Learning/Enrollment Experience"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.users import UserRole
from app.utils.permission import require_roles, get_current_user
from app.models.students import Student, SelfSignedStudent
from app.models.teachers import SelfSignedTeacher
from app.models.tuition_models import (
    TuitionBatch,
    TuitionBatchStudentMapping,
    StudentTopicProgressStatus,
)
from app.schemas.tuition.student import (
    StudentEnrollmentResponse,
    StudentTuitionListResponse,
    StudentTuitionListItem,
    AvailableBatchesResponse,
    AvailableBatchSummary,
    StudyPlanResponse,
    LessonDetailResponse,
    LessonSummary,
    TopicSummary,
    TopicDetailResponse,
    TopicFileResponse,
    TopicCompleteResponse,
    BatchScheduleResponse,
    ScheduleItemResponse,
    JoinClassResponse,
    BatchAssignmentsResponse,
    AssignmentSummary,
    StudentDashboardResponse,
    DashboardTuitionItem,
    DashboardUpcomingClass,
    DashboardRecentAssignment,
    DashboardStudyProgress,
    TuitionBatchTeacherInfo,
    TuitionBatchScheduleInfo,
)
from app.crud.tuition.student import (
    get_or_create_enrollment,
    get_student_enrollments,
    verify_student_enrollment,
    get_batch_with_lesson_plan,
    get_lesson_plan_for_batch,
    get_lessons_for_lesson_plan,
    get_lesson,
    get_topic,
    get_topics_for_lesson,
    get_files_for_topic,
    mark_topic_completed,
    get_topic_progress,
    get_lesson_progress,
    get_lesson_plan_progress,
    get_batch_schedules,
    get_schedule,
    get_class_done_record,
    get_batch_assignments,
    get_assignment,
    get_available_batches,
    get_batch_enrollment_count,
)

router = APIRouter(prefix="/tuition/student", tags=["Student Tuition"])


def _get_current_student(current_user, db: Session):
    """Get current student (regular or self-signed)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if regular student
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if student:
        return student, "student"
    
    # Check if self-signed student
    self_signed = db.query(SelfSignedStudent).filter(
        SelfSignedStudent.user_id == current_user.id
    ).first()
    if self_signed:
        return self_signed, "self_signed_student"
    
    raise HTTPException(status_code=403, detail="User is not a student")


def _serialize_batch_info(db: Session, batch: TuitionBatch):
    """Serialize basic batch info"""
    teacher_name = ""
    teacher_id = batch.teacher_id or batch.self_signed_teacher_id
    teacher_type = batch.teacher_type

    if batch.teacher_id:
        from app.models.teachers import Teacher
        teacher = db.query(Teacher).filter(Teacher.id == batch.teacher_id).first()
        if teacher:
            teacher_name = f"{teacher.first_name} {teacher.last_name}".strip()
    else:
        teacher = db.query(SelfSignedTeacher).filter(
            SelfSignedTeacher.id == batch.self_signed_teacher_id
        ).first()
        if teacher:
            teacher_name = f"{teacher.first_name} {teacher.last_name}".strip()

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "teacher_type": teacher_type,
    }


# ============================================================================
# SECTION 1: TEACHER DISCOVERY & AVAILABLE BATCHES
# ============================================================================

@router.get("/teachers", response_model=AvailableBatchesResponse)
def list_available_teachers(
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
    board: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List available teachers/batches for student discovery"""
    skip = (page - 1) * page_size
    
    batches, total = get_available_batches(
        db,
        board=board,
        class_id=class_id,
        subject_id=subject_id,
        skip=skip,
        limit=page_size,
    )
    
    batch_list = []
    for batch in batches:
        batch_info = _serialize_batch_info(db, batch)
        enrolled_count = get_batch_enrollment_count(db, batch.id)
        
        # Get subject and class names
        subject_name = batch.subject_obj.name if batch.subject_obj else ""
        class_name = batch.class_obj.name if batch.class_obj else ""
        
        batch_summary = AvailableBatchSummary(
            batch_id=batch.id,
            batch_name=batch.batch_name,
            teacher=TuitionBatchTeacherInfo(**batch_info),
            board=batch.board_id,
            class_name=class_name,
            subject_name=subject_name,
            batch_status=batch.batch_status,
            description=batch.description,
            start_date=batch.start_date,
            end_date=batch.end_date,
            batch_capacity=batch.batch_capacity,
            tuition_fee=str(batch.tuition_fee),
            study_material_fee=str(batch.study_material_fee),
            enrolled_count=enrolled_count,
            language=batch.language,
        )
        batch_list.append(batch_summary)
    
    return AvailableBatchesResponse(
        total=total,
        page=page,
        page_size=page_size,
        batches=batch_list,
    )


# ============================================================================
# SECTION 2: ENROLLMENT MANAGEMENT
# ============================================================================

@router.post("/batches/{batch_id}/join", response_model=StudentEnrollmentResponse)
def join_batch(
    batch_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Student joins/enrolls in a tuition batch"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Verify batch exists and is active
    batch = get_batch_with_lesson_plan(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    if batch.batch_status != "active":
        raise HTTPException(status_code=400, detail="Batch is not active")
    
    # Create or get enrollment
    if student_type == "student":
        mapping, created = get_or_create_enrollment(
            db, batch_id, student_id=student.id
        )
    else:
        mapping, created = get_or_create_enrollment(
            db, batch_id, self_signed_student_id=student.id
        )
    
    if not created:
        raise HTTPException(status_code=400, detail="Already enrolled in this batch")
    
    return StudentEnrollmentResponse(
        enrollment_id=mapping.id,
        batch_id=mapping.batch_id,
        enrollment_status=mapping.enrollment_status,
        payment_status=mapping.payment_status,
        joined_date=mapping.joined_date,
    )


@router.get("/my", response_model=StudentTuitionListResponse)
def list_my_enrollments(
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    board: Optional[str] = Query(None),
    class_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List student's tuition enrollments"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    skip = (page - 1) * page_size
    
    # Get enrollments
    if student_type == "student":
        enrollments, total = get_student_enrollments(
            db,
            student_id=student.id,
            skip=skip,
            limit=page_size,
            enrollment_status=status,
            board=board,
            class_id=class_id,
            subject_id=subject_id,
        )
    else:
        enrollments, total = get_student_enrollments(
            db,
            self_signed_student_id=student.id,
            skip=skip,
            limit=page_size,
            enrollment_status=status,
            board=board,
            class_id=class_id,
            subject_id=subject_id,
        )
    
    enrollment_items = []
    for enrollment in enrollments:
        batch = get_batch_with_lesson_plan(db, enrollment.batch_id)
        if not batch:
            continue
        
        batch_info = _serialize_batch_info(db, batch)
        subject_name = batch.subject_obj.name if batch.subject_obj else ""
        class_name = batch.class_obj.name if batch.class_obj else ""
        
        # Calculate progress
        lesson_plan = get_lesson_plan_for_batch(db, batch.id)
        progress = None
        if lesson_plan:
            if student_type == "student":
                lessons_done, lessons_total, topics_done, topics_total = get_lesson_plan_progress(
                    db, lesson_plan.id, student_id=student.id
                )
            else:
                lessons_done, lessons_total, topics_done, topics_total = get_lesson_plan_progress(
                    db, lesson_plan.id, self_signed_student_id=student.id
                )
            
            completion_pct = int((topics_done / topics_total * 100) if topics_total > 0 else 0)
            progress = {
                "lessons_completed": lessons_done,
                "lessons_total": lessons_total,
                "topics_completed": topics_done,
                "topics_total": topics_total,
                "completion_percentage": completion_pct,
            }
        
        schedule_info = TuitionBatchScheduleInfo(
            start_date=batch.start_date,
            end_date=batch.end_date,
            days=batch.days_of_week,
            time_slot=f"{batch.start_time} - {batch.end_time}" if batch.start_time and batch.end_time else None,
        )
        
        item = StudentTuitionListItem(
            enrollment_id=enrollment.id,
            batch_id=enrollment.batch_id,
            batch_name=batch.batch_name,
            teacher_name=batch_info["teacher_name"],
            teacher_id=batch_info["teacher_id"],
            teacher_type=batch_info["teacher_type"],
            board=batch.board_id,
            class_name=class_name,
            subject_name=subject_name,
            enrollment_status=enrollment.enrollment_status,
            payment_status=enrollment.payment_status,
            batch_status=batch.batch_status,
            joined_date=enrollment.joined_date,
            schedule=schedule_info,
            progress=progress,
        )
        enrollment_items.append(item)
    
    return StudentTuitionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        enrollments=enrollment_items,
    )


# ============================================================================
# SECTION 3: STUDY PLAN & CURRICULUM
# ============================================================================

@router.get("/batches/{batch_id}/study-plan", response_model=StudyPlanResponse)
def get_batch_study_plan(
    batch_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Get study plan for enrolled batch"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Verify enrollment
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch_id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch_id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this batch")
    
    # Get batch and lesson plan
    batch = get_batch_with_lesson_plan(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    lesson_plan = get_lesson_plan_for_batch(db, batch.id)
    if not lesson_plan:
        raise HTTPException(status_code=404, detail="No lesson plan found for batch")
    
    # Get lessons
    lessons = get_lessons_for_lesson_plan(db, lesson_plan.id)
    
    # Calculate progress and build lesson items
    lessons_completed = 0
    topics_completed = 0
    topics_total = 0
    lesson_items = []
    
    for lesson in lessons:
        # Get topics for lesson
        topics = get_topics_for_lesson(db, lesson.id)
        lesson_topics_total = len(topics)
        topics_total += lesson_topics_total
        
        # Calculate lesson progress
        if student_type == "student":
            lesson_topics_done, _ = get_lesson_progress(db, lesson.id, student_id=student.id)
        else:
            lesson_topics_done, _ = get_lesson_progress(
                db, lesson.id, self_signed_student_id=student.id
            )
        
        if lesson_topics_done == lesson_topics_total and lesson_topics_total > 0:
            lessons_completed += 1
        
        topics_completed += lesson_topics_done
        
        completion_pct = int((lesson_topics_done / lesson_topics_total * 100) if lesson_topics_total > 0 else 0)
        
        lesson_item = LessonSummary(
            lesson_id=lesson.id,
            lesson_number=lesson.display_order,
            lesson_title=lesson.lesson_title,
            lesson_objective=lesson.lesson_objective,
            topics_count=lesson_topics_total,
            topics_completed=lesson_topics_done,
            completion_percentage=completion_pct,
        )
        lesson_items.append(lesson_item)
    
    overall_pct = int((topics_completed / topics_total * 100) if topics_total > 0 else 0)
    
    subject_name = batch.subject_obj.name if batch.subject_obj else ""
    class_name = batch.class_obj.name if batch.class_obj else ""
    
    return StudyPlanResponse(
        batch_id=batch.id,
        batch_name=batch.batch_name,
        lesson_plan_id=lesson_plan.id,
        subject=subject_name,
        board=batch.board_id,
        class_name=class_name,
        total_lessons=len(lessons),
        total_topics=topics_total,
        lessons_completed=lessons_completed,
        topics_completed=topics_completed,
        overall_completion_percentage=overall_pct,
        lessons=lesson_items,
    )


@router.get("/lessons/{lesson_id}", response_model=LessonDetailResponse)
def get_lesson_details(
    lesson_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Get lesson details with topics"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Get lesson
    lesson = get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Verify enrollment in batch (via lesson plan → batch)
    lesson_plan = lesson.lesson_plan
    batch = get_batch_with_lesson_plan(db, lesson_plan.batch_id)
    
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch.id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch.id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this lesson's batch")
    
    # Get topics
    topics = get_topics_for_lesson(db, lesson.id)
    
    # Calculate progress
    if student_type == "student":
        topics_completed, topics_total = get_lesson_progress(db, lesson.id, student_id=student.id)
    else:
        topics_completed, topics_total = get_lesson_progress(
            db, lesson.id, self_signed_student_id=student.id
        )
    
    # Build topic items
    topic_items = []
    for topic in topics:
        # Get progress for this topic
        if student_type == "student":
            progress = get_topic_progress(db, topic.id, student_id=student.id)
        else:
            progress = get_topic_progress(db, topic.id, self_signed_student_id=student.id)
        
        status = progress.status if progress else StudentTopicProgressStatus.NOT_STARTED
        
        files = get_files_for_topic(db, topic.id)
        has_files = len(files) > 0
        
        topic_item = TopicSummary(
            topic_id=topic.id,
            topic_title=topic.topic_title,
            display_order=topic.display_order,
            status=status,
            has_files=has_files,
        )
        topic_items.append(topic_item)
    
    return LessonDetailResponse(
        lesson_id=lesson.id,
        lesson_number=lesson.display_order,
        lesson_title=lesson.lesson_title,
        lesson_objective=lesson.lesson_objective,
        topics=topic_items,
        topics_completed=topics_completed,
    )


@router.get("/topics/{topic_id}", response_model=TopicDetailResponse)
def get_topic_details(
    topic_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Get topic details with files and progress"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Get topic
    topic = get_topic(db, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Verify enrollment (via topic → lesson → lesson_plan → batch)
    lesson = topic.lesson
    lesson_plan = lesson.lesson_plan
    batch = get_batch_with_lesson_plan(db, lesson_plan.batch_id)
    
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch.id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch.id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this topic's batch")
    
    # Get files
    files = get_files_for_topic(db, topic.id)
    file_items = [
        TopicFileResponse(
            file_id=f.id,
            file_name=f.file_name,
            file_url=f.file_url,
            file_type=f.file_type,
            file_size=f.file_size,
            uploaded_at=f.created_at,
        )
        for f in files
    ]
    
    # Get progress
    if student_type == "student":
        progress = get_topic_progress(db, topic.id, student_id=student.id)
    else:
        progress = get_topic_progress(db, topic.id, self_signed_student_id=student.id)
    
    student_progress = None
    if progress:
        from app.schemas.tuition.student import StudentTopicProgress
        student_progress = StudentTopicProgress(
            topic_id=progress.topic_id,
            status=progress.status,
            started_at=progress.started_at,
            completed_at=progress.completed_at,
        )
    
    return TopicDetailResponse(
        topic_id=topic.id,
        topic_title=topic.topic_title,
        topic_content=topic.topic_content,
        display_order=topic.display_order,
        reference_video_link=topic.reference_video_link,
        files=file_items,
        student_progress=student_progress,
    )


@router.post("/topics/{topic_id}/complete", response_model=TopicCompleteResponse)
def mark_topic_complete(
    topic_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Mark topic as completed by student"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Get topic and verify enrollment
    topic = get_topic(db, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    lesson = topic.lesson
    lesson_plan = lesson.lesson_plan
    batch = get_batch_with_lesson_plan(db, lesson_plan.batch_id)
    
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch.id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch.id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this topic's batch")
    
    # Mark as completed (idempotent)
    if student_type == "student":
        progress = mark_topic_completed(db, topic.id, student_id=student.id)
    else:
        progress = mark_topic_completed(db, topic.id, self_signed_student_id=student.id)
    
    return TopicCompleteResponse(
        topic_id=progress.topic_id,
        status=progress.status,
        completed_at=progress.completed_at,
    )


# ============================================================================
# SECTION 4: SCHEDULES & CLASS SESSIONS
# ============================================================================

@router.get("/batches/{batch_id}/schedule", response_model=BatchScheduleResponse)
def get_batch_schedule(
    batch_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get batch schedule"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Verify enrollment
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch_id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch_id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this batch")
    
    # Get schedules
    skip = (page - 1) * page_size
    schedules, total = get_batch_schedules(
        db,
        batch_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
        skip=skip,
        limit=page_size,
    )
    
    # Build schedule items
    schedule_items = []
    for schedule in schedules:
        class_summary = None
        done_record = get_class_done_record(db, schedule.id)
        if done_record:
            class_summary = done_record.summary
        
        item = ScheduleItemResponse(
            schedule_id=schedule.id,
            class_date=schedule.class_date,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            topic=schedule.topic,
            meeting_link=None,  # Don't expose base link; use /join endpoint
            meeting_link_override=schedule.meeting_link_override,
            status=schedule.status,
            class_summary=class_summary,
        )
        schedule_items.append(item)
    
    return BatchScheduleResponse(
        total=total,
        page=page,
        page_size=page_size,
        schedules=schedule_items,
    )


@router.get("/classes/{schedule_id}/join", response_model=JoinClassResponse)
def join_live_class(
    schedule_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Get meeting link to join live class"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Get schedule
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Verify enrollment in batch
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, schedule.batch_id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, schedule.batch_id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this class's batch")
    
    # Get batch for meeting link
    batch = get_batch_with_lesson_plan(db, schedule.batch_id)
    
    # Prefer override, then batch meeting link
    meeting_link = schedule.meeting_link_override or batch.meeting_link
    if not meeting_link:
        raise HTTPException(status_code=400, detail="No meeting link configured")
    
    return JoinClassResponse(
        schedule_id=schedule.id,
        class_date=schedule.class_date,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        topic=schedule.topic,
        meeting_provider=batch.meeting_provider,
        meeting_link=meeting_link,
    )


# ============================================================================
# SECTION 5: ASSIGNMENTS
# ============================================================================

@router.get("/batches/{batch_id}/assignments", response_model=BatchAssignmentsResponse)
def get_batch_assignments_list(
    batch_id: str,
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List assignments for batch"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Verify enrollment
    if student_type == "student":
        is_enrolled = verify_student_enrollment(db, batch_id, student_id=student.id)
    else:
        is_enrolled = verify_student_enrollment(
            db, batch_id, self_signed_student_id=student.id
        )
    
    if not is_enrolled:
        raise HTTPException(status_code=403, detail="Not enrolled in this batch")
    
    # Get assignments
    skip = (page - 1) * page_size
    assignment_results, total = get_batch_assignments(db, batch_id, skip=skip, limit=page_size)
    
    # Build assignment items
    assignment_items = []
    for assignment, mapping in assignment_results:
        # Get attempt status for this student
        from app.models.assignments.assignment import StudentAssignmentAttempt
        
        attempt = None
        if student_type == "student":
            attempt = db.query(StudentAssignmentAttempt).filter(
                StudentAssignmentAttempt.assignment_id == assignment.id,
                StudentAssignmentAttempt.student_id == student.id,
            ).first()
        else:
            attempt = db.query(StudentAssignmentAttempt).filter(
                StudentAssignmentAttempt.assignment_id == assignment.id,
                StudentAssignmentAttempt.self_signed_student_id == student.id,
            ).first()
        
        attempt_status = "not_attempted"
        if attempt:
            if attempt.submitted_at:
                attempt_status = "submitted"
            elif attempt.started_at:
                attempt_status = "in_progress"
        
        item = AssignmentSummary(
            assignment_id=assignment.id,
            title=assignment.title,
            chapter=assignment.chapter,
            topic_ids=[],
            question_count=0,
            due_date=assignment.due_date,
            status=assignment.status,
            student_attempt_status=attempt_status,
        )
        assignment_items.append(item)
    
    return BatchAssignmentsResponse(
        total=total,
        page=page,
        page_size=page_size,
        assignments=assignment_items,
    )


# ============================================================================
# SECTION 6: DASHBOARD
# ============================================================================

@router.get("/dashboard", response_model=StudentDashboardResponse)
def get_student_dashboard(
    current_user = Depends(require_roles(UserRole.STUDENT, UserRole.SELF_SIGNED_STUDENT)),
    db: Session = Depends(get_db),
):
    """Get student dashboard"""
    
    # Get current student
    student, student_type = _get_current_student(current_user, db)
    
    # Get approved enrollments
    if student_type == "student":
        enrollments, _ = get_student_enrollments(db, student_id=student.id, limit=1000)
    else:
        enrollments, _ = get_student_enrollments(
            db, self_signed_student_id=student.id, limit=1000
        )
    
    # Build tuitions list
    tuitions_list = []
    upcoming_classes_all = []
    recent_assignments_all = []
    topics_total = 0
    topics_completed = 0
    
    for enrollment in enrollments:
        batch = get_batch_with_lesson_plan(db, enrollment.batch_id)
        if not batch:
            continue
        
        # Tuition item
        lesson_plan = get_lesson_plan_for_batch(db, batch.id)
        progress_pct = 0
        if lesson_plan:
            if student_type == "student":
                _, _, topics_done, topics_ttl = get_lesson_plan_progress(
                    db, lesson_plan.id, student_id=student.id
                )
            else:
                _, _, topics_done, topics_ttl = get_lesson_plan_progress(
                    db, lesson_plan.id, self_signed_student_id=student.id
                )
            progress_pct = int((topics_done / topics_ttl * 100) if topics_ttl > 0 else 0)
            topics_total += topics_ttl
            topics_completed += topics_done
        
        subject_name = batch.subject_obj.name if batch.subject_obj else ""
        teacher_info = _serialize_batch_info(db, batch)
        
        tuition_item = DashboardTuitionItem(
            batch_id=batch.id,
            batch_name=batch.batch_name,
            teacher_name=teacher_info["teacher_name"],
            subject_name=subject_name,
            progress_percentage=progress_pct,
            enrollment_status=enrollment.enrollment_status,
        )
        tuitions_list.append(tuition_item)
        
        # Upcoming classes (next 3)
        schedules, _ = get_batch_schedules(db, batch.id, limit=3)
        for schedule in schedules:
            if schedule.status != "completed":
                upcoming_classes_all.append(
                    DashboardUpcomingClass(
                        schedule_id=schedule.id,
                        class_date=schedule.class_date,
                        start_time=schedule.start_time,
                        subject_name=subject_name,
                        batch_name=batch.batch_name,
                    )
                )
        
        # Recent assignments (next 3)
        assignment_results, _ = get_batch_assignments(db, batch.id, limit=3)
        for assignment, mapping in assignment_results:
            recent_assignments_all.append(
                DashboardRecentAssignment(
                    assignment_id=assignment.id,
                    title=assignment.title,
                    batch_name=batch.batch_name,
                    due_date=assignment.due_date,
                    status=assignment.status,
                )
            )
    
    # Limit to most relevant
    upcoming_classes = upcoming_classes_all[:5]
    recent_assignments = recent_assignments_all[:5]
    
    # Overall progress
    overall_pct = int((topics_completed / topics_total * 100) if topics_total > 0 else 0)
    
    return StudentDashboardResponse(
        active_tuitions_count=len(tuitions_list),
        tuitions=tuitions_list,
        upcoming_classes=upcoming_classes,
        recent_assignments=recent_assignments,
        study_progress=DashboardStudyProgress(
            total_topics=topics_total,
            topics_completed=topics_completed,
            total_lessons=0,  # Can be enhanced
            lessons_completed=0,  # Can be enhanced
            overall_percentage=overall_pct,
        ),
    )
