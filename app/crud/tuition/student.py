"""CRUD operations for student tuition"""

from datetime import datetime, date
from typing import List, Optional, Tuple
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.tuition_models import (
    TuitionBatch,
    TuitionBatchStudentMapping,
    TuitionBatchSchedule,
    TuitionLessonPlan,
    TuitionLesson,
    TuitionLessonTopic,
    TuitionTopicFile,
    TuitionClassDoneRecord,
    TuitionLessonAssignmentMapping,
    StudentTuitionTopicProgress,
    StudentTopicProgressStatus,
    EnrollmentStatus,
)
from app.models.students import Student, SelfSignedStudent
from app.models.assignments.assignment import Assignment


# ============================================================================
# ENROLLMENT OPERATIONS
# ============================================================================

def get_or_create_enrollment(
    db: Session,
    batch_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> Tuple[TuitionBatchStudentMapping, bool]:
    """Get or create student enrollment in batch. Returns (mapping, created)"""
    
    if student_id:
        mapping = db.query(TuitionBatchStudentMapping).filter(
            and_(
                TuitionBatchStudentMapping.batch_id == batch_id,
                TuitionBatchStudentMapping.student_id == student_id,
                TuitionBatchStudentMapping.is_deleted.is_(False),
            )
        ).first()
        
        if mapping:
            return mapping, False
        
        mapping = TuitionBatchStudentMapping(
            batch_id=batch_id,
            student_id=student_id,
            student_type="student",
            enrollment_status=EnrollmentStatus.PENDING,
        )
    else:
        mapping = db.query(TuitionBatchStudentMapping).filter(
            and_(
                TuitionBatchStudentMapping.batch_id == batch_id,
                TuitionBatchStudentMapping.self_signed_student_id == self_signed_student_id,
                TuitionBatchStudentMapping.is_deleted.is_(False),
            )
        ).first()
        
        if mapping:
            return mapping, False
        
        mapping = TuitionBatchStudentMapping(
            batch_id=batch_id,
            self_signed_student_id=self_signed_student_id,
            student_type="self_signed_student",
            enrollment_status=EnrollmentStatus.PENDING,
        )
    
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping, True


def get_student_enrollments(
    db: Session,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
    enrollment_status: Optional[str] = None,
    board: Optional[str] = None,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
) -> Tuple[List[TuitionBatchStudentMapping], int]:
    """Get student enrollments with optional filters. Returns (enrollments, total_count)"""
    
    query = db.query(TuitionBatchStudentMapping).filter(
        TuitionBatchStudentMapping.is_deleted.is_(False)
    )
    
    if student_id:
        query = query.filter(TuitionBatchStudentMapping.student_id == student_id)
    elif self_signed_student_id:
        query = query.filter(TuitionBatchStudentMapping.self_signed_student_id == self_signed_student_id)
    else:
        return [], 0
    
    if enrollment_status:
        query = query.filter(TuitionBatchStudentMapping.enrollment_status == enrollment_status)
    
    # Join with batch and filter by batch properties
    if board or class_id or subject_id:
        query = query.join(
            TuitionBatch,
            TuitionBatchStudentMapping.batch_id == TuitionBatch.id,
        ).filter(TuitionBatch.is_deleted.is_(False))
        
        if board:
            query = query.filter(TuitionBatch.board_id == board)
        if class_id:
            query = query.filter(TuitionBatch.class_id == class_id)
        if subject_id:
            query = query.filter(TuitionBatch.subject_id == subject_id)
    
    total = query.count()
    enrollments = query.offset(skip).limit(limit).all()
    
    return enrollments, total


def verify_student_enrollment(
    db: Session,
    batch_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> bool:
    """Check if student is enrolled in batch"""
    
    query = db.query(TuitionBatchStudentMapping).filter(
        and_(
            TuitionBatchStudentMapping.batch_id == batch_id,
            TuitionBatchStudentMapping.is_deleted.is_(False),
        )
    )
    
    if student_id:
        query = query.filter(TuitionBatchStudentMapping.student_id == student_id)
    elif self_signed_student_id:
        query = query.filter(TuitionBatchStudentMapping.self_signed_student_id == self_signed_student_id)
    else:
        return False
    
    return query.first() is not None


# ============================================================================
# STUDY PLAN & CURRICULUM OPERATIONS
# ============================================================================

def get_batch_with_lesson_plan(db: Session, batch_id: str) -> Optional[TuitionBatch]:
    """Get batch with lesson plan"""
    return db.query(TuitionBatch).filter(
        and_(
            TuitionBatch.id == batch_id,
            TuitionBatch.is_deleted.is_(False),
        )
    ).first()


def get_lesson_plan_for_batch(db: Session, batch_id: str) -> Optional[TuitionLessonPlan]:
    """Get lesson plan for batch"""
    return db.query(TuitionLessonPlan).filter(
        and_(
            TuitionLessonPlan.batch_id == batch_id,
            TuitionLessonPlan.is_deleted.is_(False),
        )
    ).first()


def get_lessons_for_lesson_plan(
    db: Session, lesson_plan_id: str
) -> List[TuitionLesson]:
    """Get all lessons for lesson plan, ordered"""
    return db.query(TuitionLesson).filter(
        and_(
            TuitionLesson.lesson_plan_id == lesson_plan_id,
            TuitionLesson.is_deleted.is_(False),
        )
    ).order_by(TuitionLesson.display_order).all()


def get_lesson(db: Session, lesson_id: str) -> Optional[TuitionLesson]:
    """Get lesson by ID"""
    return db.query(TuitionLesson).filter(
        and_(
            TuitionLesson.id == lesson_id,
            TuitionLesson.is_deleted.is_(False),
        )
    ).first()


def get_topic(db: Session, topic_id: str) -> Optional[TuitionLessonTopic]:
    """Get topic by ID"""
    return db.query(TuitionLessonTopic).filter(
        and_(
            TuitionLessonTopic.id == topic_id,
            TuitionLessonTopic.is_deleted.is_(False),
        )
    ).first()


def get_topics_for_lesson(db: Session, lesson_id: str) -> List[TuitionLessonTopic]:
    """Get all topics for lesson, ordered"""
    return db.query(TuitionLessonTopic).filter(
        and_(
            TuitionLessonTopic.lesson_id == lesson_id,
            TuitionLessonTopic.is_deleted.is_(False),
        )
    ).order_by(TuitionLessonTopic.display_order).all()


def get_files_for_topic(db: Session, topic_id: str) -> List[TuitionTopicFile]:
    """Get all files for topic"""
    return db.query(TuitionTopicFile).filter(
        and_(
            TuitionTopicFile.topic_id == topic_id,
            TuitionTopicFile.is_deleted.is_(False),
        )
    ).all()


# ============================================================================
# TOPIC PROGRESS OPERATIONS
# ============================================================================

def get_or_create_topic_progress(
    db: Session,
    topic_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> Tuple[StudentTuitionTopicProgress, bool]:
    """Get or create topic progress. Returns (progress, created)"""
    
    if student_id:
        progress = db.query(StudentTuitionTopicProgress).filter(
            and_(
                StudentTuitionTopicProgress.topic_id == topic_id,
                StudentTuitionTopicProgress.student_id == student_id,
            )
        ).first()
        
        if progress:
            return progress, False
        
        progress = StudentTuitionTopicProgress(
            topic_id=topic_id,
            student_id=student_id,
            student_type="student",
            status=StudentTopicProgressStatus.NOT_STARTED,
        )
    else:
        progress = db.query(StudentTuitionTopicProgress).filter(
            and_(
                StudentTuitionTopicProgress.topic_id == topic_id,
                StudentTuitionTopicProgress.self_signed_student_id == self_signed_student_id,
            )
        ).first()
        
        if progress:
            return progress, False
        
        progress = StudentTuitionTopicProgress(
            topic_id=topic_id,
            self_signed_student_id=self_signed_student_id,
            student_type="self_signed_student",
            status=StudentTopicProgressStatus.NOT_STARTED,
        )
    
    db.add(progress)
    db.commit()
    db.refresh(progress)
    return progress, True


def mark_topic_completed(
    db: Session,
    topic_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> StudentTuitionTopicProgress:
    """Mark topic as completed and return progress"""
    
    progress, _ = get_or_create_topic_progress(
        db, topic_id, student_id, self_signed_student_id
    )
    
    progress.status = StudentTopicProgressStatus.COMPLETED
    progress.completed_at = datetime.utcnow()
    progress.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(progress)
    return progress


def get_topic_progress(
    db: Session,
    topic_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> Optional[StudentTuitionTopicProgress]:
    """Get topic progress for student"""
    
    if student_id:
        return db.query(StudentTuitionTopicProgress).filter(
            and_(
                StudentTuitionTopicProgress.topic_id == topic_id,
                StudentTuitionTopicProgress.student_id == student_id,
            )
        ).first()
    else:
        return db.query(StudentTuitionTopicProgress).filter(
            and_(
                StudentTuitionTopicProgress.topic_id == topic_id,
                StudentTuitionTopicProgress.self_signed_student_id == self_signed_student_id,
            )
        ).first()


def get_lesson_progress(
    db: Session,
    lesson_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> Tuple[int, int]:
    """Get lesson progress (topics_completed, topics_total). Returns (completed, total)"""
    
    topics = get_topics_for_lesson(db, lesson_id)
    total = len(topics)
    
    if total == 0:
        return 0, 0
    
    completed = 0
    for topic in topics:
        progress = get_topic_progress(db, topic.id, student_id, self_signed_student_id)
        if progress and progress.status == StudentTopicProgressStatus.COMPLETED:
            completed += 1
    
    return completed, total


def get_lesson_plan_progress(
    db: Session,
    lesson_plan_id: str,
    student_id: Optional[int] = None,
    self_signed_student_id: Optional[int] = None,
) -> Tuple[int, int, int, int]:
    """Get lesson plan progress. Returns (lessons_completed, lessons_total, topics_completed, topics_total)"""
    
    lessons = get_lessons_for_lesson_plan(db, lesson_plan_id)
    lessons_total = len(lessons)
    
    if lessons_total == 0:
        return 0, 0, 0, 0
    
    lessons_completed = 0
    topics_total = 0
    topics_completed = 0
    
    for lesson in lessons:
        topics = get_topics_for_lesson(db, lesson.id)
        lesson_topics_total = len(topics)
        topics_total += lesson_topics_total
        
        if lesson_topics_total == 0:
            lessons_completed += 1
            continue
        
        lesson_completed = 0
        for topic in topics:
            progress = get_topic_progress(db, topic.id, student_id, self_signed_student_id)
            if progress and progress.status == StudentTopicProgressStatus.COMPLETED:
                lesson_completed += 1
                topics_completed += 1
        
        if lesson_completed == lesson_topics_total:
            lessons_completed += 1
    
    return lessons_completed, lessons_total, topics_completed, topics_total


# ============================================================================
# SCHEDULE OPERATIONS
# ============================================================================

def get_batch_schedules(
    db: Session,
    batch_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[TuitionBatchSchedule], int]:
    """Get batch schedules with optional filters. Returns (schedules, total_count)"""
    
    query = db.query(TuitionBatchSchedule).filter(
        and_(
            TuitionBatchSchedule.batch_id == batch_id,
            TuitionBatchSchedule.is_deleted.is_(False),
        )
    )
    
    if from_date:
        query = query.filter(TuitionBatchSchedule.class_date >= from_date)
    if to_date:
        query = query.filter(TuitionBatchSchedule.class_date <= to_date)
    if status:
        query = query.filter(TuitionBatchSchedule.status == status)
    
    total = query.count()
    schedules = query.order_by(TuitionBatchSchedule.class_date).offset(skip).limit(limit).all()
    
    return schedules, total


def get_schedule(db: Session, schedule_id: str) -> Optional[TuitionBatchSchedule]:
    """Get schedule by ID"""
    return db.query(TuitionBatchSchedule).filter(
        and_(
            TuitionBatchSchedule.id == schedule_id,
            TuitionBatchSchedule.is_deleted.is_(False),
        )
    ).first()


def get_class_done_record(
    db: Session, schedule_id: str
) -> Optional[TuitionClassDoneRecord]:
    """Get class done record for schedule"""
    return db.query(TuitionClassDoneRecord).filter(
        and_(
            TuitionClassDoneRecord.schedule_id == schedule_id,
            TuitionClassDoneRecord.is_deleted.is_(False),
        )
    ).first()


# ============================================================================
# ASSIGNMENT OPERATIONS
# ============================================================================

def get_batch_assignments(
    db: Session,
    batch_id: str,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[Tuple[Assignment, TuitionLessonAssignmentMapping]], int]:
    """Get assignments for batch via lesson plan. Returns (assignments, total_count)"""
    
    # Get lesson plan for batch
    lesson_plan = get_lesson_plan_for_batch(db, batch_id)
    if not lesson_plan:
        return [], 0
    
    # Query assignment mappings
    query = db.query(Assignment, TuitionLessonAssignmentMapping).join(
        TuitionLessonAssignmentMapping,
        TuitionLessonAssignmentMapping.assignment_id == Assignment.id,
    ).filter(
        and_(
            TuitionLessonAssignmentMapping.lesson_plan_id == lesson_plan.id,
            Assignment.is_deleted.is_(False),
        )
    )
    
    total = query.count()
    results = query.offset(skip).limit(limit).all()
    
    return results, total


def get_assignment(db: Session, assignment_id: int) -> Optional[Assignment]:
    """Get assignment by ID"""
    return db.query(Assignment).filter(
        and_(
            Assignment.id == assignment_id,
            Assignment.is_deleted.is_(False),
        )
    ).first()


# ============================================================================
# AVAILABLE BATCHES OPERATIONS
# ============================================================================

def get_available_batches(
    db: Session,
    board: Optional[str] = None,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[TuitionBatch], int]:
    """Get available/active batches for student discovery"""
    
    query = db.query(TuitionBatch).filter(
        and_(
            TuitionBatch.is_deleted.is_(False),
            TuitionBatch.batch_status == "active",
        )
    )
    
    if board:
        query = query.filter(TuitionBatch.board_id == board)
    if class_id:
        query = query.filter(TuitionBatch.class_id == class_id)
    if subject_id:
        query = query.filter(TuitionBatch.subject_id == subject_id)
    
    total = query.count()
    batches = query.offset(skip).limit(limit).all()
    
    return batches, total


def get_batch_enrollment_count(db: Session, batch_id: str) -> int:
    """Get number of enrolled students in batch"""
    return db.query(func.count(TuitionBatchStudentMapping.id)).filter(
        and_(
            TuitionBatchStudentMapping.batch_id == batch_id,
            TuitionBatchStudentMapping.enrollment_status == EnrollmentStatus.APPROVED,
            TuitionBatchStudentMapping.is_deleted.is_(False),
        )
    ).scalar() or 0
